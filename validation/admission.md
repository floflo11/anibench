# Grader validation

Each scored task has a reference animation (correct) and 7 broken copies. A check counts for a task only if the reference passes it. A broken copy is *caught* if any of its intended checks fails on it.

| Task | Checks kept | Dropped (reference failed) | Whole image | Missed thumb | Hole left | Frozen | Center pivot | No loop | Wrong part |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T01 | G1, G2, G3, G4, G5, G6 | - | caught | caught | caught | caught | caught | caught | caught |
| T02 | G1, G2, G3, G4, G6 | G5 | caught | missed | caught | caught | n/a | caught | caught |
| T03 | G1, G2, G3, G4, G5, G6 | - | caught | missed | caught | caught | caught | caught | caught |
| T04 | G1, G3, G4, G5, G6 | G2 | caught | n/a | caught | caught | caught | caught | caught |
| T05 | G1, G3, G4, G5, G6 | G2 | caught | n/a | caught | caught | caught | caught | caught |
| T06 | G1, G3, G4, G5, G6 | G2 | caught | n/a | caught | caught | caught | caught | caught |
| T07 | G1, G2, G3, G4, G5, G6 | - | caught | missed | caught | caught | missed | missed | caught |
| T08 | G1, G3, G4, G5, G6 | G2 | caught | n/a | caught | caught | caught | caught | caught |
| T09 | G1, G2, G3, G4, G5, G6 | - | caught | missed | caught | caught | caught | caught | caught |
| T10 | G1, G2, G3, G4, G5, G6 | - | caught | missed | caught | caught | caught | caught | caught |
| T11 | G1, G2, G3, G4, G5, G6 | - | caught | missed | caught | caught | caught | caught | caught |
| T12 | G1, G3, G4, G6 | G2, G5 | caught | n/a | caught | caught | n/a | caught | caught |
| T13 | G1, G3, G4, G6 | - | caught | n/a | caught | caught | n/a | caught | caught |
| T14 | G1, G3, G4, G6 | G5 | caught | n/a | caught | caught | n/a | caught | caught |
| T15 | G1, G2, G3, G4, G6 | - | caught | missed | caught | caught | n/a | caught | caught |
| T16 | G1, G2, G3, G4, G6 | - | caught | missed | caught | caught | n/a | caught | caught |
| T17 | G1, G2, G3, G4, G6 | - | caught | caught | caught | caught | n/a | caught | caught |
| T18 | G1, G2, G3, G4, G6 | - | caught | caught | caught | caught | n/a | caught | caught |
| T19 | G1, G3, G4, G5, G6 | G2 | caught | n/a | caught | caught | caught | caught | caught |
| T20 | G1, G2, G3, G4, G5, G6 | - | caught | caught | caught | caught | caught | caught | caught |
| T21 | G1, G3, G4, G5, G6 | G2 | caught | n/a | caught | caught | caught | caught | caught |

**Broken copies caught (where an intended check applies):** Whole image 21/21; Missed thumb 4/12; Hole left 21/21; Frozen 21/21; Center pivot 12/13; No loop 20/21; Wrong part 21/21
