/**
 * The capture handoff, and the one property that matters.
 *
 * A capture must be consumed exactly once. If Screening could read it twice,
 * a back-navigation would re-screen the previous traveller's document and
 * attach their verdict to the person now standing at the counter — which is
 * the worst failure this small store can produce, and the reason `take()`
 * clears in the same call rather than exposing a separate reset.
 */
import { beforeEach, describe, expect, it } from "vitest";
import { useCapture, type PendingCapture } from "./capture";

const capture = (docType = "aadhaar"): PendingCapture => ({
  blob: new Blob(["document"], { type: "image/jpeg" }),
  docType,
  source: "camera",
  uploaded: false,
});

beforeEach(() => {
  useCapture.setState({ pending: null });
});

describe("the capture handoff", () => {
  it("hands the capture over exactly once", () => {
    const first = capture("passport");
    useCapture.getState().put(first);

    expect(useCapture.getState().take()).toBe(first);
    expect(useCapture.getState().take()).toBeNull();
  });

  it("reports nothing waiting rather than throwing", () => {
    expect(useCapture.getState().take()).toBeNull();
  });

  it("does not let one traveller's capture outlive the next", () => {
    useCapture.getState().put(capture("pan"));
    useCapture.getState().take();

    const next = capture("dl");
    useCapture.getState().put(next);

    const taken = useCapture.getState().take();
    expect(taken?.docType).toBe("dl");
    expect(useCapture.getState().pending).toBeNull();
  });

  it("carries the liveness burst through untouched", () => {
    const frames = [new Blob(["a"]), new Blob(["b"]), new Blob(["c"])];
    useCapture.getState().put({ ...capture(), liveFrames: frames });
    expect(useCapture.getState().take()?.liveFrames).toHaveLength(3);
  });
});
