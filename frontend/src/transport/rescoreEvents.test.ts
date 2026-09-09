import { afterEach, describe, expect, it, vi } from "vitest";
import { rescoreEvents, type RescoreResult } from "./socket";

const BANDS = { green_below: 0.3, amber_below: 0.7, coverage_floor: 0.7 };

function result(id: string): RescoreResult {
  return {
    event_id: id,
    doc_type: "passport",
    recorded: { band: "AMBER", score: 0.5, coverage: 0.44 },
    rescored: { band: "RED", score: 0.8, coverage: 0.44, reason: null },
    changed: true,
  };
}

function respond(body: unknown, ok = true, status = 200) {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    statusText: "",
    json: () => Promise.resolve(body),
  } as unknown as Response);
}

afterEach(() => vi.unstubAllGlobals());

describe("rescoreEvents", () => {
  it("asks for the whole page in one request", async () => {
    const fetchMock = respond({ results: ["a", "b", "c"].map(result) });
    vi.stubGlobal("fetch", fetchMock);

    await rescoreEvents(["a", "b", "c"], BANDS);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/rescore/batch");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      event_ids: ["a", "b", "c"],
      bands: BANDS,
    });
  });

  /**
   * The bug this whole refactor could plausibly introduce. The server omits an
   * event it could not re-score, so the array comes back short — and if the
   * caller zipped it against the ids it asked for, every row below the gap
   * would be relabelled with another screening's verdict. On an audit screen
   * that is a wrong verdict attributed to the wrong traveller.
   */
  it("keys results by event_id, so an omitted event cannot shift the rest", async () => {
    vi.stubGlobal("fetch", respond({ results: [result("a"), result("c")] }));

    const results = await rescoreEvents(["a", "b", "c"], BANDS);
    const keyed: Record<string, RescoreResult> = {};
    for (const r of results) keyed[r.event_id] = r;

    expect(Object.keys(keyed).sort()).toEqual(["a", "c"]);
    expect(keyed.c.event_id).toBe("c");
    expect(keyed.b).toBeUndefined();
  });

  it("surfaces the server's own sentence when the page is over the cap", async () => {
    vi.stubGlobal(
      "fetch",
      respond({ detail: "500 events asked for in one request; the limit is 200." }, false, 400),
    );

    await expect(rescoreEvents(Array(500).fill("x"), BANDS)).rejects.toThrow(
      /the limit is 200/,
    );
  });
});
