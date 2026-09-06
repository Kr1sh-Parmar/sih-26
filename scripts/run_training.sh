#!/usr/bin/env bash
# Wait for the CUDA torch download to land, install ultralytics into the
# training venv, then train and export the 22-class field detector.
#
# BUILD-TIME ONLY. Everything here runs in .venv-train, which is the only place
# torch and CUDA exist. The screening path never sees either - it loads the
# exported int8 ONNX through onnxruntime on CPU.
#
#   bash scripts/run_training.sh 100        # epochs, default 100
#
# Progress goes to var/training.log. The markers this prints (TRAIN-START,
# TRAIN-DONE, TRAIN-FAILED) are what the monitor watches for.
set -u

EPOCHS="${1:-100}"
# Pinned as a pair: torchvision 0.21 is the build that matches torch 2.6, and
# cu124 is the newest CUDA line with a 2.6 wheel.
TORCH_VER="2.6.0+cu124"
TV_VER="0.21.0+cu124"
CUDA_TAG="cu124"
PY=".venv-train/Scripts/python.exe"
LOG="var/training.log"
mkdir -p var

say() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$LOG"; }

# ---------------------------------------------------------------- wait for torch
say "waiting for CUDA torch to finish installing"
while ! "$PY" -c "import torch" >/dev/null 2>&1; do
  alive=$(powershell -NoProfile -Command \
    "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -like '*venv-train*' } | Measure-Object).Count" 2>/dev/null | tr -d '\r')
  if [ "${alive:-0}" = "0" ]; then
    say "TRAIN-FAILED torch install ended without producing torch"
    tail -5 var/train_install.log | tee -a "$LOG"
    exit 1
  fi
  sleep 20
done

say "torch present"

# ------------------------------------------------------------ install ultralytics
# Order matters, and getting it wrong cost a run. ultralytics declares only
# `torch>=1.8.0`, so pip cheerfully "upgrades" a pinned CUDA build to the newest
# PyPI wheel - which on Windows is CPU-only. That turns a 5-hour GPU run into a
# multi-day CPU one, and ultralytics reports it as `Invalid CUDA 'device=0'`
# rather than as a broken install. So ultralytics goes in FIRST, the CUDA build
# is reasserted after it, and only then is CUDA checked.
if ! "$PY" -c "import ultralytics" >/dev/null 2>&1; then
  say "installing ultralytics into the training venv"
  "$PY" -m pip install --quiet ultralytics >>"$LOG" 2>&1 || {
    say "TRAIN-FAILED ultralytics install failed"; exit 1; }
fi

# Uninstall before reinstalling, and sweep the directories by hand. Installing
# the pinned pair *over* the ones ultralytics pulled leaves a stale
# torchvision dist-info shadowing the new files: versions then report correctly
# while the C++ ops never register, and training dies on
# `operator torchvision::nms does not exist` - which looks like a torch bug
# rather than a dirty install. Cost one run to learn.
say "removing whatever torch/torchvision the ultralytics install left behind"
"$PY" -m pip uninstall -y -q torch torchvision torchaudio >>"$LOG" 2>&1 || true
rm -rf .venv-train/Lib/site-packages/torch \
       .venv-train/Lib/site-packages/torchvision \
       .venv-train/Lib/site-packages/torch-*.dist-info \
       .venv-train/Lib/site-packages/torchvision-*.dist-info 2>/dev/null || true

say "installing the pinned CUDA build: torch ${TORCH_VER}, torchvision ${TV_VER}"
"$PY" -m pip install --quiet "torch==${TORCH_VER}" "torchvision==${TV_VER}" \
  --index-url "https://download.pytorch.org/whl/${CUDA_TAG}" >>"$LOG" 2>&1 || {
  say "TRAIN-FAILED could not install the CUDA torch build"; exit 1; }

# Versions matching is not enough - the compiled ops have to actually load.
if ! "$PY" -c "
import torch, torchvision.ops as ops
ops.nms(torch.tensor([[0.,0.,1.,1.]]), torch.tensor([0.5]), 0.5)
" >/dev/null 2>&1; then
  say "TRAIN-FAILED torchvision ops did not register; the install is dirty"
  exit 1
fi

# The check that actually matters. It has to come after every install, not before.
CUDA=$("$PY" -c "import torch; print(torch.cuda.is_available())" 2>/dev/null | tr -d '\r')
if [ "$CUDA" != "True" ]; then
  say "TRAIN-FAILED CUDA unavailable after install; refusing to start a CPU run that would take days"
  "$PY" -c "import torch; print('torch is', torch.__version__)" | tee -a "$LOG"
  exit 1
fi
"$PY" -c "import torch,ultralytics; print('ultralytics',ultralytics.__version__,'torch',torch.__version__,'cuda',torch.cuda.is_available())" | tee -a "$LOG"

# ------------------------------------------------------------------------ train
say "TRAIN-START ${EPOCHS} epochs, yolo11s, 640px, RTX 3050"
if "$PY" data/tools/train_fields.py --epochs "$EPOCHS" >>"$LOG" 2>&1; then
  say "TRAIN-DONE"
  ls -la models/ 2>/dev/null | tee -a "$LOG"
  exit 0
else
  say "TRAIN-FAILED see var/training.log"
  tail -25 "$LOG"
  exit 1
fi
