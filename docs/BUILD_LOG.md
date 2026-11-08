# Build log: where AI-generated work was wrong

Each entry: date, what was wrong, how it was caught, the fix. Honest and specific; no script text.

---

## 2026-11-08 · Phase 0 · Mock provider guessed list semantics
- **What was wrong:** the first draft of `MockProvider` tried to tell "a script of responses" apart from
  "a JSON array payload" by inspecting list element types. A list of dicts matched both cases, so a test
  scripting a bad reply then a good one could have returned the wrong item.
- **How caught:** self-review of `provider.py` before the tests ran.
- **Fix:** one rule with no guessing: a list is always a script of responses (the last one repeats); a JSON
  array payload must be passed as a string.

## 2026-11-08 · Phase 0 · Rate limiter tied to one event loop
- **What was wrong:** the limiter built its `asyncio.Semaphore`/`Lock` once. The sync `call()` wrapper runs a
  fresh event loop per call, and asyncio primitives that have waited are bound to their first loop, so the
  second sync call under contention could raise "bound to a different event loop".
- **How caught:** review while wiring `llm-ping` (three sync calls in a row).
- **Fix:** the limiter re-creates its primitives whenever the running loop changes.

## 2026-11-08 · Phase 1 · Spec's emotion-tag count includes technical tags
- **What was wrong:** the spec expects 621 distinct emotion tags. The parser finds 615.
- **How caught:** Phase 1 acceptance check. I re-counted under 8 splitting rules; 621 is reproduced exactly
  when (a) a parenthetical is not split on "/" and (b) O.S., V.O. and Off-screen are counted as emotions.
  Some pack headers mix a technical tag and emotions in one bracket, e.g. `(O.S. / <emotion>, <emotion>)`. The remaining gap of 1 is the tag "continuing", which the parser treats as CONT'D.
- **Fix:** none needed in code; the parser follows the spec's own rule (tech tags separate from emotions).
  The real-pack test asserts 615 with a pointer here. All other counts match exactly (50 episodes, 3,727
  blocks: 1,754 / 1,487 / 372 / 114; 0 blocks with end < start; 102.7 min; 33 weak openings).

## 2026-11-08 · Phase 1 · Invented fixture text collided with the real pack
- **What was wrong:** the "fake" 3-episode fixture I wrote shared 25 four-word sequences with the private
  pack. Most were generic shot vocabulary ("extreme close-up on the"), but 5 were story phrasing that
  happened to match (a stock retort, a plea, a description of a gloved hand, one parenthetical, one opener).
  Generated "original" text can echo source material it has seen in the same session.
- **How caught:** `scripts/check_leaks.py` run over the fixture before anything was staged.
- **Fix:** reworded the 5 story lines; added shot-type words to the checker's format vocabulary so generic
  camera language no longer counts. Fixture is now clean.

## 2026-11-08 · Phase 2 · The house name has more spellings than the brief says
- **What was wrong:** the brief lists five spellings of one noble house's name. The code detector (rapidfuzz ratio ≥ 75,
  same first three letters) found seven variants in one cluster. One extra variant (4 episodes) is clearly the same
  house: same manor, same family. The other (1 episode) is ambiguous. The heroine's family name, which shares the
  prefix, stays separate, grouped only with its own plural.
- **How caught:** Phase 2 acceptance check, then reading the surrounding lines locally (never copied into the repo).
- **Fix:** none needed in code. The detector proposes and the bible LLM decides. The private acceptance test reads the
  expected spellings from git-ignored `data/pack_expectations.yaml` and does not assume the list is complete.

## 2026-11-08 · Phase 3 · Spec's end-snap rule leaves a flash of the next shot
- **What was wrong:** "end at cliffhanger.end + 0.3 s" cut 0.2 s *into* the next shot whenever a shot change fell
  inside that pad. That is a 6-frame flash at the end of the promo, which an editor would reject.
- **How caught:** a hand-computed unit test (`test_end_never_leaks_next_line`) expected the cut on the shot change
  and got 17.2 s instead of 17.0 s.
- **Fix:** if a camera cut falls inside the pad, end on that cut. The other rules (extend to the shot end within
  1.5 s unless a new line starts first) are unchanged.

## 2026-11-08 · Phase 4 · Names in stage directions leaked to the Cold Viewer
- **What was wrong:** the brief replaces *speaker* names with visual descriptors, but camera and action lines also
  name characters ("Close-up on <name>'s face"). The "cold" viewer would have seen name cards a scroller never sees,
  which inflates comprehension scores.
- **How caught:** reading the perceived rendering of a fixture clip while writing `render.py`.
- **Fix:** `render.unname()` swaps canonical and given names in camera, action and SFX text for "the <descriptor>".
  Names spoken in dialogue are kept, because viewers hear them. Covered by a test.

## 2026-11-08 · Phase 3 · Rate limiter throttled the offline mock
- **What was wrong:** the mock provider went through the 10-requests-per-minute limiter, so an offline run of a
  3-episode fixture took 101 s, almost all of it waiting.
- **How caught:** stage timings in the first `--provider mock` run (viewer 54 s, risk 30 s for 26 fake calls).
- **Fix:** only live calls take a rate-limit token; mock calls skip it. Full-pack mock run: 2.5 s.

## 2026-11-08 · Phase 4 · Test run wrote into the real lexicon store
- **What was wrong:** the cross-show lexicon store defaulted to `./.cache/lexicon/`, whatever cache the client used.
  A test's fake model wrote ratings into the repo's real store, and the replay test then saw one call fewer.
- **How caught:** `test_replay_reproduces_offline` failed (21 vs 22 calls).
- **Fix:** the store lives beside the client's response cache. The test now asserts what matters: every replayed
  call is a cache hit and the slate is identical.

## 2026-11-08 · Prompt change · Miner can now see next-episode atoms
- **What changed:** `miner.md` gained `{{next_peaks}}`, the atoms around the next episode's top three hotspots.
- **Why:** the brief allows flash-forwards from the next episode, but the miner only saw this episode's atom IDs, so
  it could only invent next-episode IDs (which validation would reject as `unknown_id`).

## 2026-11-08 · Phase 6 · Progress stream ended before the run finished
- **What was wrong:** the first SSE design replayed a snapshot of past events and *also* drained a queue holding the
  same events, so the stream could end early. Separately, the background job was started without keeping a reference
  to its task.
- **How caught:** `test_upload_runs_a_mock_job` never saw the slate stage. Printing the events showed a
  cancellation. Part of the cause was the test harness: FastAPI's TestClient without a `with` block starts a fresh
  event loop per request and tears it down afterwards.
- **Fix:** one append-only event list per job that each subscriber reads by index; the task reference is kept; the
  test uses a single client session (as uvicorn does). Cancellation is now reported as an error event.

## 2026-11-08 · Phase 6 · Brand red failed contrast as text
- **What was wrong:** the brief's peak red (#E8494F) measures 4.29:1 on the app background and 3.66:1 on panels, below
  the 4.5:1 AA floor for body text. The light theme's deepened amber was 4.08:1.
- **How caught:** axe-core run against every screen in both themes (2 to 23 contrast violations per screen).
- **Fix:** kept #E8494F for data marks and added a text-only `rec-ink` (#F46A6F, 4.76:1). The light theme uses deeper
  amber and teal. The phone animatic keeps dark tokens in light mode because it depicts a screen. 0 violations after.

## 2026-11-08 · Phase 6 · Slate rationale called tied scores "the best"
- **What was wrong:** the rationale picked each promo's strongest score by index rank, so when half the pool shared a
  value every one of them was described as "best … of all 130 promos".
- **How caught:** reading the Slate screenshot during the self-critique pass.
- **Fix:** rank = (strictly better + half the ties) / pool; "best" only when the score is unique.

## 2026-11-08 · Phase 6 · Sentence-initial words flagged as unexplained names
- **What was wrong:** the proper-noun detector keeps capitalised words never seen in lower case. On a small show,
  sentence-initial words such as "Search" and "Smile" qualified, and the referent check then penalised promos for
  "names a stranger cannot place". Kinship words ("Father") were flagged too.
- **How caught:** badges on the invented demo show's Slate screen; the Quality gallery listed "Father".
- **Fix:** a capital at the start of a sentence no longer counts as evidence of a name unless it is a known
  character, and kinship and title words are excluded.

## 2026-11-08 · Phase 7 · Spec asks for a public Space but private demo data in the image
- **What was wrong:** the brief ships the demo run inside the image, but a public Space's repository (and so the image
  build context) is public, which would publish the client's scripts.
- **How caught:** planning the Docker build against the confidentiality rule.
- **Fix:** the image holds no runs; `scripts/fetch_demo.py` downloads them at start from a private dataset
  (`DEMO_RUNS_URL` + `HF_TOKEN` secrets), and the access code still guards them.

## 2026-11-08 · Phase 7 · Show names slipped into committable files
- **What was wrong:** I wrote real character and house names from the pack into a docstring, two build-log entries
  and a pack test. None were full script lines, so the 4-word leak hook could not catch them, but the master prompt
  is git-ignored precisely because it names such details.
- **How caught:** a deliberate grep for show names across every committable file before the final review.
- **Fix:** replaced them with invented names or generic wording, moved the pack test's expected spellings into
  git-ignored `data/pack_expectations.yaml`, and extended `check_leaks.py` to block the pack's distinctive proper
  nouns (capitalised in the story text, never lower case, not in the system word list; 39 names).
