# OCR Confusion Patterns
#
# Living document — add new patterns as they are discovered in retrospectives.
# Format: CHAR -> SUBSTITUTES (comma-separated, ordered by frequency/impact)
# Lines starting with # are comments and ignored by the parser.
#
# Compiled from: 03082026, batch2, batch3, batch4, batch5, batch6, batch7, batch8,
#   9000 E Bloomington Fwy, 9200 E Bloomington Fwy,
#   Washington Ave Ramp, Lucy13s, Babysteps retrospectives.
#
# ── ORDERING RULE ─────────────────────────────────
# Substitutes are ordered most-common first so the brute-force loop
# reaches the highest-probability candidate with fewest API calls.

# ── Digits ────────────────────────────────────────
0 -> D, O, Q, 3, 9       # 3 added: Batch 3 TNC307→TNC007 (3→0)
1 -> 0, I, L, T, 7
3 -> 8, 0, 9             # 0 added: Batch 3 TNC307→TNC007 (0→3)
4 -> 9, A
5 -> S, 6
6 -> 5, G, 8
7 -> Z, T, 1, J
8 -> B, 3, N, 6          # N added: Batch 3 P8M309→PNG309 (8→N)
9 -> 0, 3, 4

# ── Letters ───────────────────────────────────────
B -> 8, S, G, R
C -> G, O
D -> 0, U, L             # U added: Batch 3 CLD382→CLU382 (D→U)
E -> S, F
F -> P, R, E
G -> C, Z, 6, U, R       # U added: Lucy13s JGE259→JUE259 (G→U)
H -> X, N, M, W          # X added: Batch 3 DHEH75→DXEH75 (H→X)
I -> T, 1, L
J -> Z, 2
K -> X
L -> D, I, 1
M -> N, W
N -> M, W
O -> Q, 0, D             # NEW: bidirectional partner for 0->O; Q→O and 0→O both observed
P -> F, R
Q -> O, 0                # NEW: Babysteps PAPAQ→PAPAO (Q→O never attempted before)
R -> P, B, F, G
S -> 5, B, E
T -> I, Y, 7, 1          # NEW: T→I (Babysteps BTP350→BIP350), T→Y (PTA461→PYA461)
U -> D, V, W             # D added: Batch 3 CLD382→CLU382 (U→D)
V -> U, B, Y             # NEW: 03082026 GGV718 variants; Y↔V already in Y->V
W -> M, N                # N added: Lucy13s 077ZKN→077ZXM (N→M); symmetric
X -> K, H                # H added: Batch 3 DHEH75→DXEH75 (X→H)
Y -> X, V
Z -> 7, J, G, 2
