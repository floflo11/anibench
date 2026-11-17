# Grader validation

Each scored task has a reference animation (correct) and up to 10 broken copies. A check counts for a task only if the reference passes it. A broken copy is *caught* if any of its intended checks fails on it; *n/a* means none of its intended checks was kept for the task (or the copy does not apply to the task kind). Intended checks: Whole image G1; Missed thumb G2/G2b; Hole left G3; Frozen G4; Center pivot G5; No loop G6; Wrong part G1/G4; Detach small G2/G2b; Detach tip G2/G2b; Gap seam G2/G2b. *missed (no split)*: the part never actually comes apart in that copy (reference.oracle_split draws the part alone, frame by frame, and counts its pieces), e.g. a tip left behind that the moving part slides past while still touching it; no connectivity check can see those.

| Task | Checks kept | Dropped (reference failed) | Whole image | Missed thumb | Hole left | Frozen | Center pivot | No loop | Wrong part | Detach small | Detach tip | Gap seam |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T01 | G1, G2, G2b, G3, G4, G5, G6 | - | caught | caught | caught | caught | caught | caught | caught | caught | caught | caught |
| T02 | G1, G2, G2b, G3, G4, G6 | G5 | caught | caught | caught | caught | n/a | caught | caught | caught | caught | caught |
| T03 | G1, G2, G2b, G3, G4, G5, G6 | - | caught | missed (no split) | caught | caught | caught | caught | caught | missed (no split) | caught | caught |
| T04 | G1, G2b, G3, G4, G5, G6 | G2 | caught | caught | caught | caught | caught | caught | caught | caught | caught | caught |
| T05 | G1, G2b, G3, G4, G5, G6 | G2 | caught | missed (no split) | caught | caught | caught | caught | caught | caught | caught | caught |
| T06 | G1, G2b, G3, G4, G5, G6 | G2 | caught | caught | caught | caught | caught | caught | caught | caught | caught | caught |
| T07 | G1, G2, G2b, G3, G4, G5, G6 | - | caught | missed (no split) | caught | caught | missed | missed | caught | caught | caught | caught |
| T08 | G1, G2b, G3, G4, G5, G6 | G2 | caught | caught | caught | caught | caught | caught | caught | caught | caught | caught |
| T09 | G1, G2, G2b, G3, G4, G5, G6 | - | caught | missed (no split) | caught | caught | caught | caught | caught | missed (no split) | caught | caught |
| T10 | G1, G2, G2b, G3, G4, G5, G6 | - | caught | missed (no split) | caught | caught | caught | caught | caught | missed (no split) | caught | caught |
| T11 | G1, G2, G2b, G3, G4, G5, G6 | - | caught | missed (no split) | caught | caught | caught | caught | caught | missed (no split) | caught | caught |
| T12 | G1, G2b, G3, G4, G6 | G2, G5 | caught | caught | caught | caught | n/a | caught | caught | caught | caught | caught |
| T13 | G1, G2b, G3, G4, G6 | - | caught | caught | caught | caught | n/a | caught | caught | caught | caught | n/a |
| T14 | G1, G2b, G3, G4, G6 | G5 | caught | caught | caught | caught | n/a | caught | caught | caught | caught | missed (no split) |
| T15 | G1, G2, G2b, G3, G4, G6 | - | caught | missed (no split) | caught | caught | n/a | caught | caught | missed (no split) | caught | n/a |
| T16 | G1, G2, G2b, G3, G4, G6 | - | caught | missed (no split) | caught | caught | n/a | caught | caught | missed (no split) | caught | n/a |
| T17 | G1, G2, G2b, G3, G4, G6 | - | caught | caught | caught | caught | n/a | caught | caught | caught | caught | n/a |
| T18 | G1, G2, G2b, G3, G4, G6 | - | caught | caught | caught | caught | n/a | caught | caught | caught | caught | n/a |
| T19 | G1, G2b, G3, G4, G5, G6 | G2 | caught | missed (no split) | caught | caught | caught | caught | caught | missed | caught | caught |
| T20 | G1, G2, G2b, G3, G4, G5, G6 | - | caught | caught | caught | caught | caught | caught | caught | caught | caught | caught |
| T21 | G1, G2b, G3, G4, G5, G6 | G2 | caught | missed (no split) | caught | caught | caught | caught | caught | caught | caught | caught |

**Broken copies caught (where an intended check applies):** Whole image 21/21; Missed thumb 11/21; Hole left 21/21; Frozen 21/21; Center pivot 12/13; No loop 20/21; Wrong part 21/21; Detach small 14/21; Detach tip 21/21; Gap seam 15/16

**Detachment copies caught, counting only copies where the part really comes apart:** Missed thumb 11/11; Detach small 14/15; Detach tip 20/20; Gap seam 12/12
