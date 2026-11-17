# Grader validation

Each scored task has a reference animation (correct) and up to 10 broken copies. A check counts for a task only if the reference passes it. A broken copy is *caught* if any of its intended checks fails on it; *n/a* means none of its intended checks was kept for the task (or the copy does not apply to the task kind). Intended checks: Whole image G1; Missed thumb G2/G2b/G2c; Hole left G3; Frozen G4; Center pivot G5; No loop G6; Wrong part G1/G4; Detach small G2/G2b/G2c; Detach tip G2/G2b/G2c; Gap seam G2/G2b/G2c. *missed (no split)*: the part never actually comes apart in that copy (oracle_split draws the part alone, frame by frame, and counts its pieces), e.g. a tip left behind that the moving part slides past while still touching it; no connectivity check (G2, G2b) can see those, only G2c (a piece left behind while the fitted part moves on).

| Task | Checks kept | Dropped (reference failed) | Whole image | Missed thumb | Hole left | Frozen | Center pivot | No loop | Wrong part | Detach small | Detach tip | Gap seam |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S001 | G1, G2, G2b, G2c, G3, G4, G5, G6 | - | caught | missed (no split) | caught | caught | missed | missed | caught | missed (no split) | caught | missed |
| S005 | G1, G2, G2b, G2c, G3, G4, G5, G6 | - | caught | caught | caught | caught | missed | caught | caught | caught | caught | caught |
| S009 | G1, G2, G2b, G3, G4, G5, G6 | G2c | caught | missed (no split) | missed | caught | missed | missed | caught | caught | caught | missed |
| S013 | G1, G2, G2b, G3, G4, G5, G6 | G2c | caught | missed (no split) | caught | caught | missed | caught | caught | missed (no split) | caught | missed |
| S017 | G1, G2, G2b, G2c, G3, G4, G5, G6 | - | caught | missed (no split) | caught | caught | missed | caught | caught | missed (no split) | caught | missed |
| S021 | G1, G2, G2b, G3, G4, G5, G6 | G2c | caught | caught | caught | caught | missed | caught | caught | caught | caught | missed |
| S025 | G1, G2, G2b, G3, G4, G5, G6 | G2c | caught | missed (no split) | missed | caught | missed | missed | caught | missed (no split) | caught | missed |
| S029 | G1, G2, G2b, G2c, G3, G4, G5, G6 | - | caught | caught | caught | caught | missed | caught | caught | caught | caught | missed |
| S033 | G1, G2, G2c, G3, G4, G5, G6 | G2b | caught | missed (no split) | missed | caught | missed | missed | caught | missed (no split) | missed | missed |
| S037 | G1, G2, G3, G4, G5, G6 | G2b, G2c | caught | caught | caught | caught | missed | caught | caught | missed | caught | caught |
| S041 | G1, G2, G2b, G2c, G3, G4, G5, G6 | - | caught | missed (no split) | caught | caught | missed | missed | caught | missed (no split) | caught | missed |
| S045 | G1, G2, G2c, G3, G4, G5, G6 | G2b | caught | caught | caught | caught | missed | caught | caught | caught | caught | missed |
| S049 | G1, G2, G2b, G2c, G3, G4, G5, G6 | - | caught | missed (no split) | missed | caught | missed | missed | caught | missed (no split) | caught | missed |
| S053 | G1, G2, G3, G4, G5, G6 | G2b, G2c | caught | missed (no split) | caught | caught | missed | caught | caught | missed (no split) | caught | missed |
| S057 | G1, G2, G2b, G2c, G3, G4, G5, G6 | - | caught | missed (no split) | missed | caught | missed | missed | caught | missed (no split) | caught | missed |
| S061 | G1, G2, G3, G4, G5, G6 | G2b, G2c | caught | caught | caught | caught | missed | caught | caught | missed | caught | missed |
| S065 | G1, G2, G2b, G3, G4, G5, G6 | G2c | caught | missed (no split) | missed | caught | missed | missed | caught | missed (no split) | caught | missed |
| S069 | G1, G2, G2b, G3, G4, G5, G6 | G2c | caught | caught | caught | caught | missed | caught | caught | caught | caught | caught |
| S073 | G1, G2, G2b, G2c, G3, G4, G5, G6 | - | caught | missed (no split) | missed | caught | missed | missed | caught | missed (no split) | caught | missed |
| S077 | G1, G2, G2b, G2c, G3, G4, G5, G6 | - | caught | caught | caught | caught | missed | caught | caught | caught | caught | missed |
| S081 | G1, G2, G2b, G3, G4, G5, G6 | G2c | caught | missed (no split) | caught | caught | missed | missed | caught | missed (no split) | caught | missed |
| S085 | G1, G2, G2c, G3, G4, G5, G6 | G2b | caught | missed (no split) | caught | caught | missed | caught | caught | missed (no split) | caught | missed |
| S089 | G1, G2, G2b, G3, G4, G5, G6 | G2c | caught | caught | missed | caught | missed | missed | caught | caught | caught | missed |
| S093 | G1, G2, G2b, G2c, G3, G4, G5, G6 | - | caught | caught | caught | caught | missed | caught | caught | caught | caught | missed |
| S097 | G1, G2, G2b, G2c, G3, G4, G5, G6 | - | caught | caught | caught | caught | missed | caught | caught | missed (no split) | caught | missed |
| S101 | G1, G2, G2b, G3, G4, G5, G6 | G2c | caught | caught | caught | caught | missed | caught | caught | caught | caught | missed |
| S105 | G1, G2, G2b, G3, G4, G5, G6 | G2c | caught | missed (no split) | missed | caught | missed | missed | caught | missed (no split) | caught | missed |
| S109 | G1, G2, G2b, G2c, G3, G4, G5, G6 | - | caught | caught | caught | caught | missed | caught | caught | caught | caught | missed |
| S113 | G1, G2, G2b, G2c, G3, G4, G5, G6 | - | caught | missed (no split) | caught | caught | missed | missed | caught | missed (no split) | caught | missed |
| S117 | G1, G2, G2b, G3, G4, G5, G6 | G2c | caught | caught | caught | caught | missed | caught | caught | caught | caught | missed |
| S121 | G1, G2, G2b, G2c, G3, G4, G5, G6 | - | caught | caught | caught | caught | missed | missed | caught | missed (no split) | caught | missed |
| S125 | G1, G2, G2b, G3, G4, G5, G6 | G2c | caught | missed (no split) | caught | caught | missed | caught | caught | missed (no split) | caught | missed |
| S129 | G1, G2, G2b, G3, G4, G5, G6 | G2c | caught | missed (no split) | missed | caught | missed | missed | caught | missed (no split) | caught | missed |
| S133 | G1, G2, G2b, G2c, G3, G4, G5, G6 | - | caught | caught | caught | caught | missed | caught | caught | caught | caught | missed |
| S137 | G1, G2, G2b, G2c, G3, G4, G5, G6 | - | caught | caught | caught | caught | missed | missed | caught | caught | caught | missed |
| S141 | G1, G2, G2c, G3, G4, G5, G6 | G2b | caught | caught | caught | caught | missed | caught | caught | caught | caught | missed |
| S145 | G1, G2, G2b, G3, G4, G5, G6 | G2c | caught | missed (no split) | missed | caught | missed | missed | caught | caught | caught | missed |
| S149 | G1, G2, G2b, G3, G4, G5, G6 | G2c | caught | missed (no split) | caught | caught | missed | caught | caught | caught | caught | caught |
| S153 | G1, G2, G2b, G3, G4, G5, G6 | G2c | caught | missed (no split) | missed | caught | missed | caught | caught | missed (no split) | caught | missed |
| S157 | G1, G2, G2b, G3, G4, G5, G6 | G2c | caught | missed (no split) | caught | caught | missed | caught | caught | missed (no split) | caught | missed |

**Broken copies caught (where an intended check applies):** Whole image 40/40; Missed thumb 18/40; Hole left 28/40; Frozen 40/40; Center pivot 0/40; No loop 23/40; Wrong part 40/40; Detach small 17/40; Detach tip 39/40; Gap seam 4/40

**Detachment copies caught, counting only copies where the part really comes apart:** Missed thumb 12/12; Detach small 16/18; Detach tip 39/40; Gap seam 4/40

**Which intended check fired (a copy can trip several):** Whole image G1 40; Missed thumb G2 11, G2b 10, G2c 11; Hole left G3 28; Frozen G4 40; No loop G6 23; Wrong part G1 24, G4 31; Detach small G2b 14, G2c 9; Detach tip G2 26, G2b 33, G2c 1; Gap seam G2 2, G2b 2
