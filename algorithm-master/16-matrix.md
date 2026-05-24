# 16. Matrix (2D 매트릭스)

> "2D 배열은 그냥 `int[][]` 이중 for 돌리는 거" 라고 답하면 입문자.
> 마스터는 회전을 transpose+row-reverse로 분해하고, 나선을 4 경계 좁히기로 일반화하며, Set Matrix Zeroes를 in-place O(1) 추가 공간으로 처리하고, Search a 2D Matrix II에서 우상단 시작점이 왜 결정적인지를 즉답한다.
>
> 이 챕터는 옵션값/문법 외우기 대신 **2D 인덱스의 본질·왜·연결·운영 진단**만 다룬다. 카메라 ISP, GPU GEMM, Conway's Game of Life, OpenCV warpAffine까지 매트릭스 사고는 production 어디에든 있다.

---

## 0. 인지 신호 — 이 문제는 Matrix 패턴이다

면접관이 입력으로 `int[][] grid`, `char[][] board`, `List<List<Integer>>`를 던지는 순간 6개 하위 패턴 중 하나로 분류한다.

| 신호 | 하위 패턴 | 대표 문제 |
|---|---|---|
| "이미지를 90도 회전", "행렬을 전치하라" | **회전/전치(Rotation/Transpose)** | LC 48 Rotate Image, 카카오 행렬 테두리 회전 |
| "나선 순서로 출력", "달팽이 모양으로 채워라" | **나선(Spiral)** | LC 54, LC 59, 프로그래머스 행렬 테두리 회전 |
| "0이 있는 행과 열을 모두 0으로", "in-place로" | **In-place 표시(Marker)** | LC 73 Set Matrix Zeroes |
| "단어가 격자에 있는지", "상하좌우로 이동하며 검색" | **격자 탐색(Grid DFS/BFS)** | LC 79 Word Search, LC 200 Number of Islands |
| "각 행/열이 정렬된 2D에서 target 찾기" | **정렬된 2D 검색(Sorted Matrix)** | LC 240 Search a 2D Matrix II |
| "다음 세대 상태를 계산", "주변 8칸을 보고 갱신" | **시뮬레이션(Simulation)** | LC 289 Game of Life, LC 36 Valid Sudoku |

추가 신호:
- "정사각형(NxN)이라고 명시" → 회전 가능, 비정사각형(MxN)은 회전 시 새 배열 필요
- "추가 공간 O(1)" → in-place 표시 트릭 (첫 행/열을 marker로) 또는 비트 인코딩
- "주변 8방향" → Game of Life 류 시뮬레이션, dx/dy 8쌍
- "주변 4방향 + 방문 표시" → DFS/BFS on grid (챕터 08, 09와 교차)

**감별 포인트**: "2D 자체가 본질인가?" vs "2D는 그래프의 표현일 뿐인가?"
- 본질이 2D → 이 챕터 (회전, 전치, 나선, in-place, sorted matrix)
- 그래프 표현 → DFS/BFS 챕터 (Number of Islands, 미로 최단경로)

---

## 1. 백지 그리기 — ASCII로 패턴 시각화

### 1.1 90도 회전 = transpose + 행 reverse

```
원본 (3x3)              transpose             각 행 reverse (= 시계 90도)
                       (대각선 대칭)
1 2 3                  1 4 7                  7 4 1
4 5 6      ──▶         2 5 8      ──▶         8 5 2
7 8 9                  3 6 9                  9 6 3

원본 (i,j) → transpose 후 (j,i) → reverse 후 (j, n-1-i)

검증: (0,0)=1 → 회전 후 (0, n-1)=오른쪽 위 = 1 ✓
      (0,2)=3 → 회전 후 (2, n-1)=오른쪽 아래 = 3 ✓
```

**왜 두 단계로 쪼개나?**
한 번에 (i,j) → (j, n-1-i) 매핑하면 4칸이 cycle을 이루기 때문에 (i,j), (j,n-1-i), (n-1-i,n-1-j), (n-1-j,i) 4개를 동시에 swap해야 한다. 4-way swap은 임시 변수 1개로 가능하지만, transpose+reverse 분해가 **외우기·디버깅·검증** 모두 쉽다. 라이브 코딩 환경에서는 분해 풀이가 안전하다.

**반시계 90도** = transpose + 열 reverse(또는 행 reverse + transpose). **180도** = 행 reverse + 열 reverse (= 모든 (i,j)를 (n-1-i, n-1-j)로).

### 1.2 나선 매트릭스 — 4 경계 좁히기

```
4x4 spiral:

  top=0     ┌──────────────▶┐
            │ 1  2  3  4    │
  ┌─────────┘               │
  │                         │ right=3
  │ 5  6  7  8              │
  │                         │
left=0      9 10 11 12       │
  │                         │
  │13 14 15 16              │
  └─────────────────────────┘
                bottom=3

출력 순서: 1→2→3→4 → 8→12→16 → 15→14→13 → 9→5 → 6→7 → 11→10
경계 변화: top++,  right--,  bottom--,  left++  (한 방향 끝낼 때마다)
종료 조건: top > bottom 또는 left > right
```

**왜 경계 좁히기가 본질인가?**
나선의 각 변(top row, right col, bottom row, left col)을 한 번씩 처리하고 안쪽 사각형으로 축소된다. 4개 경계 변수만으로 임의 크기 MxN을 처리한다 — 정사각형 가정도 필요 없고, 1행/1열도 자연스럽게 처리된다 (`top == bottom`일 때 한 행만 출력하고 종료).

**함정**: bottom→top 진행 시 `top != bottom` 체크 안 하면 1행짜리에서 같은 행을 두 번 출력. left→right 진행도 동일.

### 1.3 In-place 표시 트릭 — 첫 행/열을 marker로

```
Set Matrix Zeroes (LC 73): 0이 있는 행/열을 모두 0으로

순진한 방법: boolean[m] rows, boolean[n] cols → O(m+n) 공간
in-place: 첫 행/열을 그 행/열에 0이 있다는 marker로 재활용 → O(1) 공간

[원본]                  [marker 단계]              [최종]
1 1 1                   1 1 1   ┌ row[0]에 0 있음
1 0 1        ──▶        1 0 1   │ 표시 (0,0)=0    ──▶  1 0 1
1 1 1                   1 1 1   └ col[1]에 0 있음        0 0 0
                                  표시 (0,1)=0           1 0 1
                                                          
선행 작업: 첫 행/첫 열에 원래 0이 있었는지 별도 boolean 2개로 기록
순서가 중요: 안쪽부터 0으로 칠한 뒤, 마지막에 첫 행/열 처리
```

**순서 의존성이 본질**:
1. `firstRowZero`, `firstColZero` 두 boolean 저장 (첫 행/열 자체에 0이 원래 있었는지)
2. (1,1)부터 스캔: arr[i][j]==0이면 arr[i][0]=0, arr[0][j]=0 (marker)
3. (1,1)부터 다시 스캔: arr[i][0]==0 또는 arr[0][j]==0이면 arr[i][j]=0
4. 첫 행/열 처리: `firstRowZero`면 첫 행 전체 0, `firstColZero`면 첫 열 전체 0

만약 1번을 빼먹고 3번에서 첫 행/열까지 처리하면 marker가 자기 자신을 침범하여 결과가 망가진다.

### 1.4 Sorted Matrix Search — 우상단 시작의 결정성

```
LC 240: 각 행 오름차순, 각 열 오름차순. target=5 찾기

  1  4  7 11 15        시작 = 우상단 (0, n-1) = 15
  2  5  8 12 19        15 > 5 → 왼쪽으로 (col--)
  3  6  9 16 22        11 > 5 → ...
 10 13 14 17 24        7 > 5  → 왼쪽
 18 21 23 26 30        4 < 5  → 아래로 (row++)
                       5 == 5 → 찾음 ✓

규칙: cur > target → col-- (오른쪽은 전부 더 크니 버림)
     cur < target → row++ (위쪽은 전부 더 작으니 버림)
시간: O(M+N), 한 step마다 행 또는 열 하나가 제거됨
```

**왜 우상단인가?**
시작점이 가져야 할 조건: "한 방향 = 무조건 크다, 다른 방향 = 무조건 작다." 우상단(0, n-1)은 왼쪽=작음, 아래=큼. 좌하단(m-1, 0)도 동일 (오른쪽=큼, 위=작음). 좌상단/우하단은 두 방향 모두 같은 부호라 결정 불가 — 이분 탐색이 깨진다.

**왜 O(M+N)인가?**
한 step마다 row 또는 col이 정확히 1 감소/증가. 최악은 좌하단까지 (m-1)+(n-1) step. 행렬 전체 MxN 대비 압도적이다.

### 1.5 Game of Life — Ghost array 또는 비트 인코딩

```
주변 8칸 카운트:
  ┌─┬─┬─┐
  │N│N│N│   N: neighbors (8개)
  ├─┼─┼─┤   C: 현재 셀
  │N│C│N│   다음 상태는 N의 alive 개수에 따라 결정
  ├─┼─┼─┤
  │N│N│N│
  └─┴─┴─┘

규칙:
- alive + (live neighbors < 2) → dead (underpopulation)
- alive + (2 or 3 live neighbors) → alive
- alive + (> 3 live neighbors) → dead (overpopulation)
- dead + (exactly 3 live neighbors) → alive (reproduction)

문제: 현재 셀을 갱신하면 이웃 셀의 카운트가 오염됨 → 동시 갱신 필요

해법 1 (ghost): board 복사 → O(MN) 공간
해법 2 (비트): 0=dead→dead, 1=alive→alive, 2=alive→dead, 3=dead→alive
              현재 상태는 & 1, 다음 상태는 >> 1
              한 번 더 스캔하여 >> 1로 확정
```

**비트 인코딩의 본질**:
"현재 상태 + 다음 상태를 한 셀에 동시 저장" → 추가 공간 O(1). 카운트할 때는 `& 1`로 현재만 읽고, 마지막에 `>> 1`로 다음만 남긴다. production 시뮬레이션(셀룰러 오토마타, 그래픽 효과)에서 메모리가 빠듯할 때 쓰는 기법.

---

## 2. 직관과 정의

### 2.1 Row/Col 인덱스 사고

2D 배열은 본질적으로 **1D 메모리의 row-major 매핑**.

```
Java/Kotlin int[3][4]:
  메모리 레이아웃: [row0_col0, row0_col1, row0_col2, row0_col3,
                  row1_col0, row1_col1, ..., row2_col3]
  arr[i][j] 접근 = arr_base + i * 4 + j

C/C++의 진짜 row-major와 달리 Java는 "배열의 배열" — 각 행은 독립 객체.
→ 행 단위 swap은 포인터 교환만으로 O(1) (행 reverse 시 활용)
→ 행마다 길이가 다를 수 있음 (jagged array)
```

**시니어 운영 연결**: Cache locality.
- 같은 행 내에서 j를 증가시키며 접근 → 캐시 친화적 (연속 메모리)
- 같은 열을 내려가며 접근 (i 증가) → 캐시 미스 폭증 (행마다 다른 cache line)
- 행렬 곱 `C = A * B`에서 B의 열을 미리 전치하면 캐시 미스 1/10로 감소 — BLAS, NumPy, JNI BLAS 백엔드의 기본 트릭

라이브 코딩에서 "2D 순회 어떻게 할래?" 질문에 "이중 for, 바깥은 i(row), 안은 j(col)" 가 안전. 반대로 하면 캐시 친화도 떨어진다고 한 줄 코멘트 가능.

### 2.2 In-place 변환의 메모리 트레이드오프

| 방식 | 추가 공간 | 코드 복잡도 | 디버깅 |
|---|---|---|---|
| **새 배열 생성** | O(MN) | 낮음 | 쉬움 |
| **마커 배열** (boolean[m], boolean[n]) | O(M+N) | 중간 | 중간 |
| **첫 행/열 marker** | O(1) | 높음 | 어려움 (순서 의존성) |
| **비트 인코딩** | O(1) | 높음 | 매우 어려움 |

**production 판단**:
- 이미지 처리(OpenCV, PIL) → 보통 새 배열. 원본 보존이 중요.
- 임베디드(메모리 < 256KB) → in-place 필수. 약간의 코드 복잡도는 감수.
- 게임 보드, 셀룰러 오토마타 → ghost buffer (더블 버퍼링) 표준.

라이브 코딩에서 "추가 공간 O(1)" 요구가 명시되지 않으면 가독성 우선. 명시되면 in-place 트릭 필수.

### 2.3 시뮬레이션에서 Ghost Array vs 비트 인코딩

```
[Ghost Array — Double Buffering]
        ┌──────┐         ┌──────┐
read ─▶ │curr  │         │next  │ ◀─ write
        └──┬───┘         └──┬───┘
           └─── swap ───────┘
GPU 그래픽, 게임 엔진의 표준. 메모리 2배지만 동시성 안전.

[Bit Encoding — In-place]
arr[i][j] = (next_state << 1) | curr_state
한 셀에 2개 상태 동시 저장. 메모리 1배. 후처리 1회 더.
```

**왜 둘 다 알아야 하나?**
면접관이 "메모리를 줄이려면?" 꼬리질문 시 비트 인코딩으로 답. 반대로 "병렬화하려면?" 시 ghost array가 자연스러움 (read-only buffer는 동시 읽기 안전).

---

## 3. Java 템플릿

### 3.1 90도 회전 (Transpose + Row Reverse)

```java
// LC 48 Rotate Image — NxN 정사각형, 시계방향 90도, in-place
public void rotate(int[][] matrix) {
    int n = matrix.length;

    // 1. transpose: (i, j) <-> (j, i), i < j인 상삼각만 swap
    for (int i = 0; i < n; i++) {
        for (int j = i + 1; j < n; j++) {
            int tmp = matrix[i][j];
            matrix[i][j] = matrix[j][i];
            matrix[j][i] = tmp;
        }
    }

    // 2. 각 행 reverse
    for (int i = 0; i < n; i++) {
        int left = 0, right = n - 1;
        while (left < right) {
            int tmp = matrix[i][left];
            matrix[i][left] = matrix[i][right];
            matrix[i][right] = tmp;
            left++;
            right--;
        }
    }
}
```

**왜 `j = i + 1`인가?**
transpose는 대각선 기준 대칭. `i == j`는 대각선 자기 자신 (swap 불필요), `j < i`는 이미 처리된 쌍. 상삼각만 돌면 정확히 N(N-1)/2 swap.

**반시계 변형**:
```java
// transpose + 열 reverse (= 행 reverse + transpose)
for (int j = 0; j < n; j++) {
    int top = 0, bot = n - 1;
    while (top < bot) {
        int tmp = matrix[top][j];
        matrix[top][j] = matrix[bot][j];
        matrix[bot][j] = tmp;
        top++; bot--;
    }
}
```

### 3.2 나선 매트릭스 (Spiral)

```java
// LC 54 Spiral Matrix — MxN, 외부에서 안쪽으로 나선
public List<Integer> spiralOrder(int[][] matrix) {
    List<Integer> result = new ArrayList<>();
    if (matrix == null || matrix.length == 0) return result;

    int top = 0, bottom = matrix.length - 1;
    int left = 0, right = matrix[0].length - 1;

    while (top <= bottom && left <= right) {
        // → top row: left to right
        for (int j = left; j <= right; j++) result.add(matrix[top][j]);
        top++;

        // ↓ right col: top to bottom
        for (int i = top; i <= bottom; i++) result.add(matrix[i][right]);
        right--;

        // ← bottom row: right to left (행이 남아 있을 때만)
        if (top <= bottom) {
            for (int j = right; j >= left; j--) result.add(matrix[bottom][j]);
            bottom--;
        }

        // ↑ left col: bottom to top (열이 남아 있을 때만)
        if (left <= right) {
            for (int i = bottom; i >= top; i--) result.add(matrix[i][left]);
            left++;
        }
    }
    return result;
}
```

**두 개의 if가 본질**:
1행 또는 1열만 남았을 때 bottom→top 또는 right→left 진행을 막지 않으면 중복 출력. 4번 갱신(top++, right--, bottom--, left++) 후 경계가 교차되면 종료.

```java
// LC 59 Spiral Matrix II — 1..n^2을 나선으로 채우기
public int[][] generateMatrix(int n) {
    int[][] m = new int[n][n];
    int top = 0, bottom = n - 1, left = 0, right = n - 1;
    int num = 1;

    while (top <= bottom && left <= right) {
        for (int j = left; j <= right; j++) m[top][j] = num++;
        top++;
        for (int i = top; i <= bottom; i++) m[i][right] = num++;
        right--;
        if (top <= bottom) {
            for (int j = right; j >= left; j--) m[bottom][j] = num++;
            bottom--;
        }
        if (left <= right) {
            for (int i = bottom; i >= top; i--) m[i][left] = num++;
            left++;
        }
    }
    return m;
}
```

### 3.3 Set Matrix Zeroes (In-place)

```java
// LC 73 Set Matrix Zeroes — O(1) 추가 공간
public void setZeroes(int[][] matrix) {
    int m = matrix.length, n = matrix[0].length;
    boolean firstRowZero = false, firstColZero = false;

    // 1. 첫 행/열에 원래 0이 있는지 기록
    for (int j = 0; j < n; j++) if (matrix[0][j] == 0) { firstRowZero = true; break; }
    for (int i = 0; i < m; i++) if (matrix[i][0] == 0) { firstColZero = true; break; }

    // 2. 안쪽 스캔: 0 발견 시 marker를 첫 행/열에 기록
    for (int i = 1; i < m; i++) {
        for (int j = 1; j < n; j++) {
            if (matrix[i][j] == 0) {
                matrix[i][0] = 0;
                matrix[0][j] = 0;
            }
        }
    }

    // 3. 안쪽 다시 스캔: marker에 따라 0으로 칠함
    for (int i = 1; i < m; i++) {
        for (int j = 1; j < n; j++) {
            if (matrix[i][0] == 0 || matrix[0][j] == 0) {
                matrix[i][j] = 0;
            }
        }
    }

    // 4. 첫 행/열 처리 (마지막에 — marker 자체를 침범하지 않기 위해)
    if (firstRowZero) for (int j = 0; j < n; j++) matrix[0][j] = 0;
    if (firstColZero) for (int i = 0; i < m; i++) matrix[i][0] = 0;
}
```

**순서가 절대적**: 4번을 먼저 하면 marker가 다 0이 되어 모든 셀이 0이 됨. 1번을 빼먹으면 첫 행/열 자체에 있던 원래 0과 marker가 구분 안 됨.

### 3.4 Search a 2D Matrix II (우상단 시작)

```java
// LC 240 — 각 행 오름차순, 각 열 오름차순. O(M+N)
public boolean searchMatrix(int[][] matrix, int target) {
    if (matrix == null || matrix.length == 0) return false;
    int m = matrix.length, n = matrix[0].length;
    int row = 0, col = n - 1;  // 우상단 시작

    while (row < m && col >= 0) {
        if (matrix[row][col] == target) return true;
        else if (matrix[row][col] > target) col--;  // 오른쪽은 더 크니 버림
        else row++;  // 위쪽은 더 작으니 버림
    }
    return false;
}
```

**좌하단 시작 변형**:
```java
int row = m - 1, col = 0;
while (row >= 0 && col < n) {
    if (matrix[row][col] == target) return true;
    else if (matrix[row][col] > target) row--;  // 아래쪽은 더 크니 버림
    else col++;  // 왼쪽은 더 작으니 버림
}
```

### 3.5 Game of Life (비트 인코딩 in-place)

```java
// LC 289 — 현재(bit 0) + 다음(bit 1)을 동시 저장
public void gameOfLife(int[][] board) {
    int m = board.length, n = board[0].length;
    int[] dx = {-1, -1, -1, 0, 0, 1, 1, 1};
    int[] dy = {-1, 0, 1, -1, 1, -1, 0, 1};

    // 1. 다음 상태 계산하여 bit 1에 저장
    for (int i = 0; i < m; i++) {
        for (int j = 0; j < n; j++) {
            int live = 0;
            for (int k = 0; k < 8; k++) {
                int ni = i + dx[k], nj = j + dy[k];
                if (ni >= 0 && ni < m && nj >= 0 && nj < n) {
                    live += board[ni][nj] & 1;  // 현재 상태만 카운트
                }
            }
            int cur = board[i][j] & 1;
            int next;
            if (cur == 1) next = (live == 2 || live == 3) ? 1 : 0;
            else          next = (live == 3) ? 1 : 0;
            board[i][j] |= (next << 1);  // bit 1에 next 저장
        }
    }

    // 2. bit 1을 bit 0으로 옮겨 확정
    for (int i = 0; i < m; i++) {
        for (int j = 0; j < n; j++) {
            board[i][j] >>= 1;
        }
    }
}
```

**왜 `& 1`로 현재 읽나?**
이웃 칸의 다음 상태가 이미 bit 1에 쓰여 있어도 `& 1`은 원래 현재 상태만 추출 — 동시 갱신이 깨지지 않음.

### 3.6 Word Search (DFS + 방문 표시)

```java
// LC 79 — board에서 word를 찾기. 상하좌우 이동, 한 셀 한 번
public boolean exist(char[][] board, String word) {
    int m = board.length, n = board[0].length;
    for (int i = 0; i < m; i++) {
        for (int j = 0; j < n; j++) {
            if (dfs(board, word, 0, i, j)) return true;
        }
    }
    return false;
}

private boolean dfs(char[][] b, String w, int idx, int i, int j) {
    if (idx == w.length()) return true;
    if (i < 0 || i >= b.length || j < 0 || j >= b[0].length) return false;
    if (b[i][j] != w.charAt(idx)) return false;

    char saved = b[i][j];
    b[i][j] = '#';  // 방문 표시 (in-place)

    boolean found = dfs(b, w, idx + 1, i + 1, j)
                 || dfs(b, w, idx + 1, i - 1, j)
                 || dfs(b, w, idx + 1, i, j + 1)
                 || dfs(b, w, idx + 1, i, j - 1);

    b[i][j] = saved;  // backtrack — 원상 복구
    return found;
}
```

**왜 `boolean[][] visited` 대신 `'#'`?**
추가 공간 O(1), 또한 같은 셀을 두 번 방문 금지를 한 자리에서 표현. backtrack 시 반드시 복구 — 안 하면 다른 시작점에서의 탐색이 망가짐.

### 3.7 Valid Sudoku (Hash 기반 검증)

```java
// LC 36 — 9x9 보드가 유효한지. 한 행/열/3x3 박스에 중복 없으면 OK
public boolean isValidSudoku(char[][] board) {
    Set<String> seen = new HashSet<>();
    for (int i = 0; i < 9; i++) {
        for (int j = 0; j < 9; j++) {
            char c = board[i][j];
            if (c == '.') continue;
            String inRow = c + "@row" + i;
            String inCol = c + "@col" + j;
            String inBox = c + "@box" + (i / 3) + "-" + (j / 3);
            if (!seen.add(inRow) || !seen.add(inCol) || !seen.add(inBox)) return false;
        }
    }
    return true;
}
```

**왜 String key 1개로 통합?**
3개의 Set을 따로 두는 풀이도 동등하지만, 단일 Set + tagged key가 의도 가독성 + 짧은 코드. production에서 "이 셀이 어떤 제약을 위반했는가" 로깅 시 tag가 그대로 메시지가 된다.

---

## 4. Kotlin 템플릿

### 4.1 90도 회전

```kotlin
fun rotate(matrix: Array<IntArray>) {
    val n = matrix.size
    // transpose
    for (i in 0 until n) {
        for (j in i + 1 until n) {
            val tmp = matrix[i][j]
            matrix[i][j] = matrix[j][i]
            matrix[j][i] = tmp
        }
    }
    // 각 행 reverse — Kotlin은 IntArray.reverse() 표준
    for (row in matrix) row.reverse()
}
```

`IntArray.reverse()`는 in-place O(N) — 새 배열 alloc 없음. `Array<IntArray>`인 점이 핵심 (Kotlin의 `Array<Int>`는 boxing되어 느림).

### 4.2 나선 매트릭스

```kotlin
fun spiralOrder(matrix: Array<IntArray>): List<Int> {
    val result = mutableListOf<Int>()
    if (matrix.isEmpty()) return result

    var top = 0
    var bottom = matrix.size - 1
    var left = 0
    var right = matrix[0].size - 1

    while (top <= bottom && left <= right) {
        for (j in left..right) result.add(matrix[top][j])
        top++
        for (i in top..bottom) result.add(matrix[i][right])
        right--
        if (top <= bottom) {
            for (j in right downTo left) result.add(matrix[bottom][j])
            bottom--
        }
        if (left <= right) {
            for (i in bottom downTo top) result.add(matrix[i][left])
            left++
        }
    }
    return result
}
```

`downTo`가 가독성 핵심. Java는 `for (int j = right; j >= left; j--)`, Kotlin은 `for (j in right downTo left)`.

### 4.3 Set Matrix Zeroes

```kotlin
fun setZeroes(matrix: Array<IntArray>) {
    val m = matrix.size
    val n = matrix[0].size
    var firstRowZero = (0 until n).any { matrix[0][it] == 0 }
    var firstColZero = (0 until m).any { matrix[it][0] == 0 }

    for (i in 1 until m) {
        for (j in 1 until n) {
            if (matrix[i][j] == 0) {
                matrix[i][0] = 0
                matrix[0][j] = 0
            }
        }
    }
    for (i in 1 until m) {
        for (j in 1 until n) {
            if (matrix[i][0] == 0 || matrix[0][j] == 0) matrix[i][j] = 0
        }
    }
    if (firstRowZero) for (j in 0 until n) matrix[0][j] = 0
    if (firstColZero) for (i in 0 until m) matrix[i][0] = 0
}
```

`any { ... }`는 short-circuit — 첫 0 발견 시 break. boolean 두 줄을 표현식 한 줄로.

### 4.4 Search a 2D Matrix II

```kotlin
fun searchMatrix(matrix: Array<IntArray>, target: Int): Boolean {
    if (matrix.isEmpty()) return false
    var row = 0
    var col = matrix[0].size - 1
    while (row < matrix.size && col >= 0) {
        when {
            matrix[row][col] == target -> return true
            matrix[row][col] > target -> col--
            else -> row++
        }
    }
    return false
}
```

`when` 표현식이 if-else 사다리보다 가독성. 3분기 분류가 즉시 보임.

### 4.5 Game of Life

```kotlin
fun gameOfLife(board: Array<IntArray>) {
    val m = board.size
    val n = board[0].size
    val dirs = listOf(-1 to -1, -1 to 0, -1 to 1, 0 to -1, 0 to 1, 1 to -1, 1 to 0, 1 to 1)

    for (i in 0 until m) {
        for (j in 0 until n) {
            var live = 0
            for ((dx, dy) in dirs) {
                val ni = i + dx; val nj = j + dy
                if (ni in 0 until m && nj in 0 until n) {
                    live += board[ni][nj] and 1
                }
            }
            val cur = board[i][j] and 1
            val next = if (cur == 1) (if (live == 2 || live == 3) 1 else 0)
                       else          (if (live == 3) 1 else 0)
            board[i][j] = board[i][j] or (next shl 1)
        }
    }
    for (i in 0 until m) for (j in 0 until n) board[i][j] = board[i][j] shr 1
}
```

Kotlin의 bitwise는 `and`, `or`, `shl`, `shr` — 연산자가 아니라 infix 함수. `ni in 0 until m`이 경계 체크 가독성 압도적.

### 4.6 Word Search

```kotlin
fun exist(board: Array<CharArray>, word: String): Boolean {
    val m = board.size; val n = board[0].size
    fun dfs(idx: Int, i: Int, j: Int): Boolean {
        if (idx == word.length) return true
        if (i !in 0 until m || j !in 0 until n) return false
        if (board[i][j] != word[idx]) return false

        val saved = board[i][j]
        board[i][j] = '#'
        val found = dfs(idx + 1, i + 1, j)
                 || dfs(idx + 1, i - 1, j)
                 || dfs(idx + 1, i, j + 1)
                 || dfs(idx + 1, i, j - 1)
        board[i][j] = saved
        return found
    }
    for (i in 0 until m) for (j in 0 until n) if (dfs(0, i, j)) return true
    return false
}
```

내부 `fun dfs` 로컬 함수가 closure로 board, word를 캡쳐 — Java라면 외부 메서드 + 파라미터로 받아야 함.

---

## 5. 시간/공간 복잡도

| 패턴 | 시간 | 공간 (추가) | 근거 |
|---|---|---|---|
| 90도 회전 (transpose+reverse) | O(N²) | O(1) | 모든 셀 1~2회 방문, 임시 변수 1개 |
| 나선 출력 | O(M·N) | O(M·N) 출력용 | 각 셀 정확히 1회 방문 |
| Set Matrix Zeroes (in-place) | O(M·N) | O(1) | 3번 스캔, marker는 첫 행/열에 |
| Search 2D Matrix II | O(M+N) | O(1) | 매 step마다 행 or 열 1 감소 |
| Game of Life (비트) | O(M·N·8) = O(M·N) | O(1) | 각 셀당 이웃 8 카운트 |
| Word Search (DFS) | O(M·N·4^L) | O(L) 재귀 스택 | L=단어 길이, 매 위치 4분기 |
| Valid Sudoku | O(81) = O(1) | O(81) = O(1) | 9x9 고정 |

**왜 회전이 O(N²)이고 회전 K번이 O(K·N²) 아닌가?**
K % 4로 줄인다. 0/1/2/3회 회전만 본질. K=10^9이어도 K%4만 적용. 면접 꼬리질문에서 자주 나오는 함정.

**시니어 운영 관점**:
- 이미지 회전(4K=3840x2160): N² ≈ 8M 픽셀, in-place는 메모리 7.9MB 절약 (RGBA 32-bit 기준). 모바일 카메라 ISP에서 결정적.
- 행렬 곱 O(N³) → Strassen O(N^2.807), Coppersmith-Winograd O(N^2.373). 실전은 cache-oblivious blocking + SIMD. 면접에서는 "naive O(N³)이지만 BLAS는 cache blocking으로 10x" 정도 언급.

---

## 6. 대표 문제

### 6.1 LC 48 — Rotate Image

**요약**: NxN 정사각형 행렬을 시계방향 90도 회전. in-place 필수.

**접근**: transpose (대각선 대칭) + 각 행 reverse. 한 줄에 4-way swap도 가능하지만 분해 풀이가 디버깅 압승.

**Java** (3.1 참조)

**Kotlin** (4.1 참조)

**복잡도**: O(N²) 시간, O(1) 공간.

**함정**:
- 비정사각형(MxN)을 회전하려면 새 배열 `int[N][M]` 필요 (in-place 불가)
- transpose에서 `j = 0`부터 돌리면 두 번 swap → 원본 복구됨 (반드시 `j = i + 1`)
- 반시계 90도는 transpose + 열 reverse (또는 행 reverse + transpose)
- 180도는 행 reverse + 열 reverse만으로 충분 (transpose 불필요)

---

### 6.2 LC 54 — Spiral Matrix

**요약**: MxN 행렬을 나선 순서로 출력.

**접근**: 4 경계 변수(top, bottom, left, right) 좁히기. 각 변마다 한 번 처리하고 갱신.

**Java** (3.2 참조)

**Kotlin** (4.2 참조)

**복잡도**: O(M·N) 시간, O(M·N) 출력 공간 (in-place 변형 아님).

**함정**:
- 1행 또는 1열만 남으면 bottom→top, right→left 진행에서 중복 출력 — 두 if 체크 필수
- "달팽이 모양으로" 한국어 문제 (프로그래머스)도 동일 패턴
- 시작점/방향이 다른 변형(중앙에서 바깥으로, 반시계 등)은 dx/dy 방향 배열 + step 카운트로 일반화 가능

---

### 6.3 LC 59 — Spiral Matrix II

**요약**: 1부터 n²까지를 nxn 행렬에 나선으로 채우기.

**접근**: LC 54와 동일 구조, 출력 대신 num++ 대입.

**Java** (3.2 참조)

**복잡도**: O(N²) 시간, O(N²) 공간 (결과 행렬).

**함정**: 정사각형이므로 두 if 체크가 필요 없을 것 같지만, n=1일 때 여전히 필요. 안전하게 항상 체크.

---

### 6.4 LC 73 — Set Matrix Zeroes

**요약**: 0이 있는 셀의 행과 열을 모두 0으로. in-place, 추가 공간 O(1).

**접근**: 첫 행/열을 marker로 재활용. firstRowZero/firstColZero를 별도 boolean으로 저장.

**Java** (3.3 참조)

**Kotlin** (4.3 참조)

**복잡도**: O(M·N) 시간, O(1) 공간.

**함정**:
- 순서: marker → 안쪽 칠하기 → 첫 행/열 처리. 뒤바꾸면 marker가 자신을 침범.
- firstRowZero/firstColZero를 안 받으면 첫 행/열의 원래 0과 marker가 구분 불가.
- O(M+N) 추가 공간 풀이(boolean[m] rows, boolean[n] cols)는 한 단계 쉬운 변형. 면접에서 "더 줄이려면?" 시 in-place로 진화.

---

### 6.5 LC 240 — Search a 2D Matrix II

**요약**: 각 행이 좌→우 오름차순, 각 열이 위→아래 오름차순인 MxN 행렬에서 target 검색.

**접근**: 우상단(0, n-1) 또는 좌하단(m-1, 0)에서 시작. 비교 결과에 따라 한 방향만 이동.

**Java** (3.4 참조)

**Kotlin** (4.4 참조)

**복잡도**: O(M+N) 시간, O(1) 공간.

**왜 이분탐색이 아닌가?**
1D 정렬 배열은 binary search O(log N). 2D에서도 각 행을 binary search 하면 O(M log N) — O(M+N)보다 느릴 수 있음 (N << M일 때 역전). 우상단 풀이가 일반적으로 압승.

**함정**:
- 좌상단/우하단 시작은 결정 불가 (양방향 모두 같은 부호)
- "각 행이 정렬, 각 행의 첫 원소가 이전 행 마지막보다 큼"인 LC 74는 사실상 1D — flatten 후 binary search O(log(MN))

---

### 6.6 LC 289 — Game of Life

**요약**: Conway's Game of Life 다음 세대 계산. in-place.

**접근**: 비트 인코딩 (bit 0=현재, bit 1=다음). 또는 ghost array 복사 후 갱신.

**Java** (3.5 참조)

**Kotlin** (4.5 참조)

**복잡도**: O(M·N) 시간, O(1) 공간(비트), O(M·N) 공간(ghost).

**꼬리질문**:
- "보드가 무한이라면?" → 살아있는 셀만 HashSet에 저장, 이웃이 살아있는 dead 셀만 후보로 (Hashlife는 캐싱으로 더 빠름).
- "병렬화하려면?" → ghost array가 자연스러움 (read-only 동시 읽기 안전). 비트 인코딩은 동시 갱신 시 race condition.

**함정**:
- 경계 체크 누락하면 ArrayIndexOutOfBounds
- `& 1` 안 쓰고 `board[ni][nj]`를 직접 카운트하면 이미 갱신된 이웃을 잘못 셈
- 마지막 `>>` 후처리 빼먹으면 결과가 2배 (bit 1만 남음)

---

### 6.7 LC 79 — Word Search

**요약**: 격자에서 단어를 상하좌우 인접 셀로 이동하며 찾기. 한 셀은 한 번만.

**접근**: DFS + 방문 표시 (`'#'`로 임시 교체, backtrack 시 복구).

**Java** (3.6 참조)

**Kotlin** (4.6 참조)

**복잡도**: O(M·N·4^L) 시간 (L=word 길이), O(L) 재귀 스택.

**최적화**:
- 첫 글자 빈도가 낮은 쪽에서 시작 (board에 'a'가 적으면 word를 뒤집어 'z'부터)
- Trie를 쓰면 LC 212 Word Search II (여러 단어 동시) — 시간 O(M·N·4^L) → 공통 prefix 공유

**함정**:
- 방문 표시 복구 안 하면 다른 시작점에서 탐색 망가짐
- `boolean[][] visited` 풀이는 동일하지만 추가 공간 O(MN)
- 같은 셀 재사용 허용 시 (변형) 무한 루프 가능 — 문제 조건 정독 필수

---

### 6.8 LC 36 — Valid Sudoku

**요약**: 9x9 스도쿠 부분 보드가 유효한지 (각 행, 열, 3x3 박스에 1-9 중복 없음).

**접근**: HashSet 1개에 tagged key 저장 (`"5@row3"`, `"5@col7"`, `"5@box1-2"`).

**Java** (3.7 참조)

**복잡도**: O(81) = O(1) 시간/공간 (9x9 고정).

**함정**:
- 빈 칸 `'.'`은 건너뜀 — 완성 여부 검사가 아니라 유효성 검사
- 박스 인덱스: `i/3`, `j/3` (0~2)
- 9x9이 아닌 일반 NxN 스도쿠 변형은 박스 크기 sqrt(N) 가정

---

### 6.9 프로그래머스 — 카펫

**요약**: 갈색 격자 brown, 노란색 격자 yellow가 주어지고 카펫의 (가로, 세로) 크기를 구하라. 가로 ≥ 세로, 가운데 노란색 직사각형이 갈색 테두리에 둘러싸임.

**접근**:
- 총 격자 = brown + yellow = w * h
- 노란색 = (w - 2) * (h - 2)
- 약수 분해: w * h의 약수쌍 중 (w-2)*(h-2) == yellow, w ≥ h 만족하는 것 찾기

**Java**:
```java
public int[] solution(int brown, int yellow) {
    int total = brown + yellow;
    for (int h = 3; h * h <= total; h++) {
        if (total % h == 0) {
            int w = total / h;
            if ((w - 2) * (h - 2) == yellow) return new int[]{w, h};
        }
    }
    return new int[]{};
}
```

**Kotlin**:
```kotlin
fun solution(brown: Int, yellow: Int): IntArray {
    val total = brown + yellow
    for (h in 3..Int.MAX_VALUE) {
        if (h * h > total) break
        if (total % h == 0) {
            val w = total / h
            if ((w - 2) * (h - 2) == yellow) return intArrayOf(w, h)
        }
    }
    return intArrayOf()
}
```

**복잡도**: O(√(brown+yellow)) — 약수 쌍은 √N까지만 탐색.

**함정**:
- h ≥ 3 (테두리 + 안쪽 최소 1)
- 가로 ≥ 세로 조건 — w = total/h, h ≤ w 이므로 h*h ≤ total
- 직접 2D 매트릭스를 만들 필요 없음 — 수학적 약수 문제로 환원

---

### 6.10 프로그래머스 — 행렬의 곱셈

**요약**: arr1 (n×m), arr2 (m×k) 행렬 곱.

**접근**: 기본 정의 `C[i][j] = Σ A[i][k] * B[k][j]`. 삼중 for.

**Java**:
```java
public int[][] solution(int[][] arr1, int[][] arr2) {
    int n = arr1.length, m = arr1[0].length, k = arr2[0].length;
    int[][] result = new int[n][k];
    for (int i = 0; i < n; i++) {
        for (int j = 0; j < k; j++) {
            int sum = 0;
            for (int t = 0; t < m; t++) {
                sum += arr1[i][t] * arr2[t][j];
            }
            result[i][j] = sum;
        }
    }
    return result;
}
```

**Kotlin**:
```kotlin
fun solution(arr1: Array<IntArray>, arr2: Array<IntArray>): Array<IntArray> {
    val n = arr1.size; val m = arr1[0].size; val k = arr2[0].size
    val result = Array(n) { IntArray(k) }
    for (i in 0 until n) {
        for (j in 0 until k) {
            var sum = 0
            for (t in 0 until m) sum += arr1[i][t] * arr2[t][j]
            result[i][j] = sum
        }
    }
    return result
}
```

**복잡도**: O(N·M·K).

**시니어 운영 관점**:
- naive 삼중 for는 cache miss 폭증 (arr2[t][j] 접근이 열 방향)
- 실전: ikj 순서로 바꾸기 (`for i, for k, for j: C[i][j] += A[i][k] * B[k][j]`) — 가장 안쪽 j 루프가 연속 메모리
- BLAS (OpenBLAS, MKL): cache blocking + SIMD + 멀티스레드로 10~100x
- 면접 답변 패턴: "O(NMK) 기본, 캐시 친화를 위해 ikj 순서, production은 BLAS"

---

### 6.11 카카오 — 행렬 테두리 회전하기

**요약**: rows×cols 행렬에 1부터 rows*cols를 채우고, queries로 (r1,c1,r2,c2) 직사각형 테두리를 시계방향 1칸 회전. 각 쿼리의 최솟값 반환.

**접근**: 각 쿼리마다
1. 좌상단 값 백업
2. 좌측 변: 아래→위로 한 칸씩 끌어올림
3. 상단 변: 우→좌로 한 칸씩
4. 우측 변: 위→아래로 한 칸씩
5. 하단 변: 좌→우로 한 칸씩
6. 좌상단의 우측 셀에 백업값 대입
7. 회전 중 본 모든 값의 min 기록

**Java**:
```java
public int[] solution(int rows, int cols, int[][] queries) {
    int[][] board = new int[rows][cols];
    int num = 1;
    for (int i = 0; i < rows; i++)
        for (int j = 0; j < cols; j++)
            board[i][j] = num++;

    int[] answer = new int[queries.length];
    for (int q = 0; q < queries.length; q++) {
        int r1 = queries[q][0] - 1, c1 = queries[q][1] - 1;
        int r2 = queries[q][2] - 1, c2 = queries[q][3] - 1;

        int saved = board[r1][c1];
        int min = saved;

        // 좌측: (r1+1..r2, c1) → (r1..r2-1, c1)
        for (int i = r1; i < r2; i++) {
            board[i][c1] = board[i + 1][c1];
            min = Math.min(min, board[i][c1]);
        }
        // 하단: (r2, c1+1..c2) → (r2, c1..c2-1)
        for (int j = c1; j < c2; j++) {
            board[r2][j] = board[r2][j + 1];
            min = Math.min(min, board[r2][j]);
        }
        // 우측: (r1..r2-1, c2) → (r1+1..r2, c2)
        for (int i = r2; i > r1; i--) {
            board[i][c2] = board[i - 1][c2];
            min = Math.min(min, board[i][c2]);
        }
        // 상단: (r1, c1+1..c2) → (r1, c2..c1+1) 방향이라 c2부터 c1+1까지
        for (int j = c2; j > c1 + 1; j--) {
            board[r1][j] = board[r1][j - 1];
            min = Math.min(min, board[r1][j]);
        }
        board[r1][c1 + 1] = saved;
        min = Math.min(min, saved);

        answer[q] = min;
    }
    return answer;
}
```

**Kotlin**:
```kotlin
fun solution(rows: Int, cols: Int, queries: Array<IntArray>): IntArray {
    val board = Array(rows) { i -> IntArray(cols) { j -> i * cols + j + 1 } }
    val answer = IntArray(queries.size)

    for ((q, qry) in queries.withIndex()) {
        val r1 = qry[0] - 1; val c1 = qry[1] - 1
        val r2 = qry[2] - 1; val c2 = qry[3] - 1
        val saved = board[r1][c1]
        var min = saved

        for (i in r1 until r2) { board[i][c1] = board[i + 1][c1]; min = minOf(min, board[i][c1]) }
        for (j in c1 until c2) { board[r2][j] = board[r2][j + 1]; min = minOf(min, board[r2][j]) }
        for (i in r2 downTo r1 + 1) { board[i][c2] = board[i - 1][c2]; min = minOf(min, board[i][c2]) }
        for (j in c2 downTo c1 + 2) { board[r1][j] = board[r1][j - 1]; min = minOf(min, board[r1][j]) }
        board[r1][c1 + 1] = saved
        min = minOf(min, saved)
        answer[q] = min
    }
    return answer
}
```

**복잡도**: 쿼리당 O((r2-r1) + (c2-c1)) = O(rows+cols), 총 O(Q·(rows+cols)).

**함정**:
- 1-indexed 입력 → 0-indexed 변환 필수
- 회전 방향 (시계 vs 반시계) 확인
- 좌상단 백업 잊으면 데이터 손실
- 테두리 길이 = 2*(높이 + 너비) - 4 (모서리 중복 제거)

---

## 7. 함정·엣지케이스 — 면접관이 묻기 전에 짚어라

### 7.1 빈 입력 / null

```java
if (matrix == null || matrix.length == 0 || matrix[0].length == 0) {
    return /* 적절한 기본값 */;
}
```

`matrix.length`만 체크하고 `matrix[0].length`를 안 보면 `new int[5][0]` 같은 0열 배열에서 NPE.

### 7.2 행 길이가 다를 때 (jagged array)

Java의 `int[][]`는 행마다 길이가 다를 수 있다. 면접 입력은 보통 직사각형이지만, production에서는 jagged 가능.

```java
// 안전한 패턴
for (int i = 0; i < matrix.length; i++) {
    for (int j = 0; j < matrix[i].length; j++) {  // matrix[0].length가 아닌 matrix[i].length
        ...
    }
}
```

회전·전치는 정사각형 가정 필요 — 비정사각형이면 새 배열 필수.

### 7.3 In-place 변환의 순서 의존성

- Set Matrix Zeroes: marker → 안쪽 처리 → 첫 행/열. 한 단계라도 뒤집으면 망가짐
- Rotate Image: transpose → row reverse. 둘 다 in-place지만 순서 결정적
- Game of Life: bit 1에 next 저장 → 전체 스캔 후 shift. shift를 셀마다 즉시 하면 다음 이웃 카운트 오염

### 7.4 Boundary 갱신 누락 (Spiral)

```java
// 잘못된 코드 — 1행짜리에서 중복 출력
for (int j = left; j <= right; j++) result.add(matrix[top][j]);
top++;
for (int i = top; i <= bottom; i++) result.add(matrix[i][right]);
right--;
// if (top <= bottom) 빠짐 → 1행짜리에서 bottom row를 다시 출력
for (int j = right; j >= left; j--) result.add(matrix[bottom][j]);
```

### 7.5 정사각형이 아닐 때 회전 안 됨

```
3x2 → 90도 회전 → 2x3 (차원이 바뀜)

1 2          5 3 1
3 4    →     6 4 2
5 6          (in-place 불가)
```

면접에서 "MxN을 회전하라"면 새 배열 `int[N][M]`을 만들고 `result[j][m-1-i] = matrix[i][j]`.

### 7.6 dx/dy 방향 배열의 길이

- 4방향 (상하좌우): `dx={-1,1,0,0}, dy={0,0,-1,1}` — Word Search, Number of Islands
- 8방향 (상하좌우+대각): Game of Life, 체스 King 이동
- 8방향 나이트: `dx={-2,-1,1,2,2,1,-1,-2}, dy={1,2,2,1,-1,-2,-2,-1}`
- 비스듬한 보드(육각): 행이 짝/홀일 때 dx/dy가 다름

방향 잘못 쓰면 답 자체가 틀림. 항상 dx[k], dy[k]가 짝지어진 같은 index인지 확인.

### 7.7 오버플로우

행렬 곱에서 큰 수: `int * int`가 int로 평가되어 오버플로우. `(long) a[i][k] * b[k][j]` 캐스팅 필수 (값이 ±2^31에 가까울 때).

좌표 인덱스는 보통 int로 충분하지만 prefix sum 결합 시 long 캐스팅 점검.

---

## 8. 꼬리질문 트리

### Q1. "회전을 K번 하면?"
- K % 4로 줄임. 0/1/2/3회만 의미 있음.
- K=10^9이어도 O(N²)으로 끝남.

### Q2. "임의 각도 회전?"
- 매트릭스 곱 (회전 변환 행렬). `[cos θ, -sin θ; sin θ, cos θ]`
- 픽셀 좌표가 정수가 아닐 수 있음 → 보간(bilinear, bicubic)
- OpenCV `warpAffine`, Java AWT `AffineTransform`
- 면접 답변: "선형대수 변환 행렬, 픽셀 보간이 핵심"

### Q3. "메모리를 더 줄이려면?"
- Set Matrix Zeroes: 이미 O(1)
- Game of Life: 비트 인코딩 (O(1)) → 메모리 1배. ghost는 2배.
- 회전: 4-way swap (in-place, 임시 변수 1개) — 이미 O(1)
- 더 줄일 수 있는 건 보통 "추가 자료구조" 부분이지 원본 자체는 아님

### Q4. "행/열 캐시 친화도?"
- 행 단위 순회 (`for i, for j`)가 캐시 친화적 — 연속 메모리
- 열 단위 (`for j, for i`)는 매 접근이 다른 cache line
- 행렬 곱 ikj 순서, transpose 후 곱하기 등이 production 기법
- "캐시 라인이 64B, int 16개 → 한 번 미스에 16개 prefetch" 정도 언급

### Q5. "스트리밍 매트릭스(행이 한 줄씩 들어옴)?"
- 회전·전치: 전체를 모아야 함 (마지막 행이 첫 열이 되므로)
- Set Matrix Zeroes: 한 번 더 스캔하려면 모아야 함. 또는 첫 패스에서 행 단위 정보 누적
- Game of Life: 슬라이딩 윈도우(3행 버퍼)로 가능 — 메모리 O(N) (한 행 크기 * 3)

### Q6. "병렬화하려면?"
- Game of Life: 셀 단위 독립 → 완벽한 병렬 (단, ghost array 사용 시)
- 행렬 곱: 행 단위/블록 단위 병렬 (BLAS, MKL이 자동)
- 회전: 4-way swap의 각 cycle 독립 → 병렬 가능하나 cache 경쟁
- Set Matrix Zeroes: 1패스(0 찾기)는 병렬, 2패스(칠하기)는 별도 단계

### Q7. "Sparse matrix라면?"
- 대부분이 0이면 `Map<Pair<Int,Int>, Int>` 또는 CSR(Compressed Sparse Row) 형식
- Set Matrix Zeroes는 0 좌표만 추적 → O(K) 공간 (K=0의 수)
- 행렬 곱은 sparse-sparse 최적화 알고리즘 별도

---

## 9. 다른 패턴과의 연결

### 9.1 DFS/BFS on Grid (챕터 08, 09)

격자가 입력일 때 가장 자주 만나는 패턴.

| 문제 | 격자 본질? | 그래프 본질? |
|---|---|---|
| LC 200 Number of Islands | △ | ◎ (DFS/BFS) |
| LC 79 Word Search | ◎ | ○ (DFS + backtrack) |
| LC 994 Rotting Oranges | △ | ◎ (BFS multi-source) |
| LC 48 Rotate Image | ◎ | × |
| LC 73 Set Matrix Zeroes | ◎ | × |

격자 → 그래프 변환: 각 셀이 노드, 인접 셀과 edge. dx/dy 배열로 표현.

### 9.2 2D Prefix Sum (챕터 15)

```
prefix[i+1][j+1] = matrix[i][j]
                 + prefix[i][j+1]
                 + prefix[i+1][j]
                 - prefix[i][j]

(r1,c1)~(r2,c2) 직사각형 합 =
  prefix[r2+1][c2+1] - prefix[r1][c2+1] - prefix[r2+1][c1] + prefix[r1][c1]
```

- LC 304 Range Sum Query 2D — 매트릭스 전처리 O(MN), 쿼리 O(1)
- 이미지 적분(Integral Image): Viola-Jones 얼굴 검출의 핵심
- 면접 꼬리질문 "범위 합 K번 묻는다" → prefix sum

### 9.3 DP on Grid (챕터 12)

```
LC 62 Unique Paths:      dp[i][j] = dp[i-1][j] + dp[i][j-1]
LC 64 Minimum Path Sum:  dp[i][j] = grid[i][j] + min(dp[i-1][j], dp[i][j-1])
LC 221 Maximal Square:   dp[i][j] = min(left, top, top-left) + 1 (현재 cell이 1일 때)
LC 1143 LCS:             dp[i][j] = 두 문자열의 i, j까지 매칭
```

매트릭스 자체가 입력이거나, 매트릭스 형태의 DP 테이블. 공간 최적화로 `int[][] dp`를 `int[] prev, curr` 또는 1D rolling으로 줄이는 트릭이 단골.

### 9.4 Graph Adjacency Matrix (챕터 11)

`int[N][N]` adjacency matrix는 매트릭스 그 자체. Floyd-Warshall은 매트릭스 갱신.

```
dist[i][j] = min(dist[i][j], dist[i][k] + dist[k][j])  // 모든 k에 대해
```

O(N³) — N=400 한계. N이 더 크면 Dijkstra (인접 리스트, O((V+E) log V)).

### 9.5 Linear Algebra → ML / GPU

- 행렬 곱 (GEMM): cuBLAS, cuDNN의 핵심 커널. 딥러닝 forward/backward의 거의 전부
- transpose는 attention의 Q·K^T에 핵심
- CCD/CMOS 픽셀 행렬 → Bayer demosaic → RGB 행렬 → ISP 파이프라인
- JPEG: 8x8 블록의 DCT (이산 코사인 변환) — 매트릭스 변환

---

## 10. 시니어 운영 관점 — Production에서 매트릭스 사고

### 10.1 이미지 처리 파이프라인

```
[RAW 센서]              [RGB 매트릭스]          [최종 JPEG]
Bayer pattern  ──▶     demosaic        ──▶    rotate/crop/resize
4032x3024              3-channel              transpose for column-major libs
12-bit ADC             ISP (denoise,           DCT 8x8 blocks
                       white balance)
```

카메라 회전: EXIF 메타데이터로 표시만 하거나 (in-place 불가능), 실제 픽셀 회전 (transpose+reverse). 모바일은 보통 메타데이터 + 디스플레이 시점 회전.

### 10.2 게임 보드 / 셀룰러 오토마타

- Conway's Game of Life는 1970년 발표 이래 universal Turing machine 증명, glider gun, replicator 등 무한한 패턴 공장
- 실전 응용: 화재 시뮬레이션 (각 셀=숲, 이웃에 불이 있으면 확률적 발화), 도시 성장 (각 셀=토지 용도), 전염병 모델 (SIR)
- 매트릭스 사고의 본질은 "지역 규칙 + 동시 갱신"

### 10.3 GPU GEMM (General Matrix Multiplication)

```
딥러닝 forward: y = Wx + b
- W: (output_dim, input_dim) 매트릭스
- x: (input_dim, batch) 매트릭스
- y: (output_dim, batch) = W @ x + b

cuBLAS sgemm 호출 → GPU의 수천 코어가 블록 단위 병렬
Tensor Core (V100, A100, H100) → 4x4 또는 16x16 매트릭스를 1 cycle에
```

면접에서 ML 인프라 얘기 시 "GEMM이 워크로드의 80% 이상" 정도는 알아야 함. 매트릭스 자체가 ML의 데이터 구조.

### 10.4 OpenCV / ImageMagick의 매트릭스 연산

- `cv::Mat`: row-major, 메모리 연속 보장 (필요시 `.clone()` 후 처리)
- 회전: `warpAffine(src, dst, M, size)` — M은 2x3 변환 행렬
- 전치: `cv::transpose(src, dst)` — SIMD 최적화
- 채널 분리: BGR → 3개 1채널 매트릭스

production에서는 "직접 회전 짜지 마라, OpenCV/PIL 써라" — 단, 알고리즘은 알고 있어야 디버깅 가능.

### 10.5 Spreadsheet / Excel 엔진

- 셀 = (row, col), 값/수식 저장
- 매트릭스의 sparse 표현 (대부분 빈 셀)
- "0이 있는 행/열 모두 0으로" → 조건부 서식, pivot table 흔한 연산
- 회전 = transpose (Excel의 "전치 붙여넣기")

### 10.6 진단 케이스: "특정 행만 응답 시간이 느려요"

production에서 매트릭스 형태 데이터(예: 사용자×상품 추천 점수 행렬)가 sparse한 경우, 캐시 친화도가 행마다 다를 수 있다.

- 행이 dense → cache hit 좋음
- 행이 sparse → 매 접근 cache miss
- 해결: CSR 형식으로 재구성, 또는 dense 부분과 sparse 부분 분리

매트릭스 사고는 단순히 회전·전치가 아니라 **메모리 레이아웃의 이해**가 본질이다.

---

## 11. 마무리 — 백지 마스터 체크리스트

다음을 백지에서 30초~5분 안에 풀어낼 수 있다면 이 챕터 마스터.

- [ ] 90도 시계 회전 = transpose + 행 reverse, 반시계 = transpose + 열 reverse, 180도 = 행 reverse + 열 reverse
- [ ] 나선 매트릭스의 4 경계 좁히기 + 두 if 체크 이유
- [ ] Set Matrix Zeroes의 3단계 순서 (firstRow/Col 저장 → marker → 칠하기 → 첫 행/열)
- [ ] Search 2D Matrix II에서 우상단 시작이 결정적인 이유
- [ ] Game of Life 비트 인코딩 (`& 1`로 현재, `<< 1`로 next, `>> 1`로 확정)
- [ ] Word Search의 방문 표시 + backtrack 복구
- [ ] 회전 K번 = K%4
- [ ] 행렬 곱 ikj 순서가 캐시 친화적
- [ ] dx/dy 4방향/8방향 배열 즉시 작성
- [ ] in-place 변환의 메모리/복잡도 트레이드오프
- [ ] 격자 문제가 본질 2D인지, 그래프인지 30초 분류

---

**다음**: 16개 패턴을 모두 마쳤다면 통합 복습 — 무작위 문제를 보고 30초 안에 패턴 분류 + 5분에 코드 + 10분에 엣지 케이스까지. hellointerview.com / programmers.co.kr / leetcode.com의 random 모드로 훈련.
