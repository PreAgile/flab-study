# 10. Backtracking (백트래킹)

> "조합·순열 = for 루프 돌리는 거" 라고 답하면 입문자.
> 마스터는 **백트래킹 = DFS + 상태 되돌리기 + Pruning**의 3단 구조를 보고, 결정 트리(decision tree)를 머릿속에서 펼친 뒤, **선택 → 재귀 → 되돌리기(undo)** 3단 boilerplate를 30초에 쓴다. 그리고 N-Queen·스도쿠·Word Search가 본질적으로 같은 패턴임을 안다.
>
> 본질: **"모든 유효한 해를 전수 탐색하되, 무효 가지는 즉시 자른다."** 이게 SAT solver, DB query planner의 join order 탐색, constraint satisfaction problem과 같은 뿌리다.

---

## 0. 목차

1. 인지 신호
2. 백지 그리기 (decision tree + pruning)
3. 직관과 정의
4. Java 템플릿 6종
5. Kotlin 템플릿 6종
6. 시간/공간 복잡도
7. 대표 문제 7개 풀이
8. 함정·엣지케이스
9. 꼬리질문 트리
10. 다른 패턴과의 연결
11. 시니어 운영 매핑

---

## 1. 인지 신호 — "이 문제는 백트래킹"

문제 설명에서 다음 단어/패턴이 보이면 머릿속에 즉시 백트래킹 boilerplate가 떠올라야 한다.

| 키워드 | 예시 | 패턴 |
|---|---|---|
| **"모든 ~을 구하라"** | 모든 순열, 모든 조합, 모든 부분집합 | 전수 탐색 |
| **"유효한 모든 ~"** | 유효한 괄호 조합, 유효한 IP, 유효한 단어 | constraint + pruning |
| **"~가지 경우의 수"** (단, 단순 곱셈 안 되는 경우) | N-Queen 개수, 스도쿠 해 개수 | search tree 카운트 |
| **"중복 허용" / "중복 금지"** | Combination Sum, Combinations | used[] vs 시작 인덱스 |
| **퍼즐 문제** | 스도쿠, N-Queen, 미로 모든 경로, 단어 검색 | 격자 + 백트래킹 |
| **"k개를 골라 ~"** | nCk 조합 | 시작 인덱스 패턴 |
| **"순서가 중요" + "전부"** | 순열 nPk | used[] 패턴 |
| **"가지치기 가능"** | "조건 위반 시 즉시 종료" | pruning이 핵심 |

**역신호 (백트래킹 아님)**:
- "최단 경로" → BFS (백트래킹은 모든 경로, BFS는 첫 도달).
- "최대/최소 값 하나만" + "중복 부분 문제" → DP.
- "그냥 1개 해" + "지역 선택으로 답 나옴" → Greedy.

**핵심 분류 질문 3개**:
1. **"답이 1개냐, 모두냐?"** — 모두면 백트래킹, 1개+최적이면 DP/Greedy.
2. **"중복 부분 문제가 있냐?"** — 있으면 DP로 전환 가능, 없으면 백트래킹.
3. **"가지치기 조건이 명확하냐?"** — 명확하면 pruning이 진짜 줄여줌, 모호하면 brute force와 같음.

---

## 2. 백지 그리기 — Decision Tree와 Pruning

### 2.1 백트래킹의 3단 사이클 — 모든 풀이의 뿌리

```
   ┌─────────────────────────────────┐
   │   1. 선택 (choose)               │
   │      path.add(option)            │
   │      used[option] = true         │
   ├─────────────────────────────────┤
   │   2. 재귀 (explore)              │
   │      backtrack(next_state)       │
   ├─────────────────────────────────┤
   │   3. 되돌리기 (unchoose / undo) │
   │      path.removeLast()           │
   │      used[option] = false        │
   └─────────────────────────────────┘
```

이 3줄이 빠지거나 순서가 틀리면 백트래킹이 아니다. **add → recurse → remove**. 면접관 앞에서 이 3줄을 못 쓰면 끝이다.

### 2.2 Decision Tree — [1, 2, 3]의 모든 순열

```
                              [ ]              ← root: 빈 path
                  /            |            \
              choose 1     choose 2      choose 3
                /              |              \
              [1]             [2]             [3]
            /     \         /     \         /     \
        ch.2    ch.3     ch.1    ch.3     ch.1    ch.2
          /       \       /       \         /       \
       [1,2]   [1,3]   [2,1]   [2,3]    [3,1]   [3,2]
         |       |       |       |        |       |
       ch.3    ch.2    ch.3    ch.1     ch.2    ch.1
         |       |       |       |        |       |
      [1,2,3] [1,3,2] [2,1,3] [2,3,1] [3,1,2] [3,2,1]   ← leaf: 결과 6개
```

- **leaf**: path.size == n, 결과에 복사해서 추가
- **branch**: 아직 안 쓴 원소 중에서 다음 선택
- **edge**: "choose i" = 그 원소를 path에 push

각 leaf까지 가는 길이가 1개의 순열. 트리의 leaf 수 = `n!`. **트리 모양을 시각화하지 못하면 디버깅 불가능**.

### 2.3 Pruning — 가지치기가 일어나는 가지

```
N-Queen, n=4의 부분 트리 (column choice)

                            (row=0, no queen yet)
            /          /         \         \
          c=0         c=1        c=2        c=3
           |           |          |          |
         (row=1)     (row=1)    (row=1)    (row=1)
        /  |  \      /  |  \     ...        ...
      c=0 c=1 c=2  c=0 c=1 c=2
       ✘   ✘   ✘   ✘   ✘   ✓
       |   |   |   |   |   |
     같은  대각 대각 같은 대각  계속
     col  공격 공격  col  공격  탐색

       ↑ 여기서 backtrack: 즉시 무효 → 자식 트리 전체 절단
```

`✘` 가지에서 **자식 트리 전체를 안 가는 게 pruning**. brute force 대비 수십~수천 배 빠른 이유.

**Pruning 종류 3가지**:

| 종류 | 의미 | 예시 |
|---|---|---|
| **infeasibility pruning** | 제약 위반 → 즉시 컷 | N-Queen 대각 공격, Sudoku 중복 |
| **bound pruning** | 현재 누적이 최적/목표 초과 → 컷 | Combination Sum에서 `sum > target` |
| **symmetry pruning** | 같은 답이 다른 가지에서 또 나옴 → 한 번만 | Permutations II 중복 처리 (정렬+skip) |

### 2.4 두 가지 핵심 패턴 — `used[]` vs `시작 인덱스`

**순열 (순서 중요, 모든 원소 사용)** → `used[]`

```
[1,2,3] 순열
   used = [F,F,F]
   각 분기마다 안 쓴 모든 원소 시도
   → [1,2,3], [1,3,2], [2,1,3], [2,3,1], [3,1,2], [3,2,1]  (6개 = 3!)
```

**조합 (순서 무시, 중복 없음)** → `start index`

```
[1,2,3]에서 2개 조합
   start=0 → [1, ...]:  start=1 → [1,2], [1,3]
   start=0 → [2, ...]:  start=2 → [2,3]
   start=0 → [3, ...]:  (start=3 → 더 없음)
   → [1,2], [1,3], [2,3]  (3개 = 3C2)

   "이전 원소는 다시 고르지 않는다" = i >= start 강제
```

**부분집합 (조합의 모든 크기 합집합)** → `start index` + 모든 노드가 결과

```
[1,2,3] 부분집합 = "각 원소 포함 or 미포함" 결정 트리
                  ┌──────────[ ]────────────┐
              not 1          ┃          incl 1
                ┃            ┃           [1]
        ┌───────┴───┐       OR    ┌──────┴────┐
      not 2       incl 2        not 2      incl 2
        ┃         [2]              [1]       [1,2]
       ...        ...              ...        ...

   결과: 8개 = 2^3 (각 원소 2가지 선택)
```

### 2.5 한 줄 본질

> **백트래킹 = DFS + 상태 (add/remove) + Pruning.**
> DFS는 그래프/트리 탐색, 백트래킹은 **암묵적 결정 트리**를 탐색 (트리를 명시적으로 구축하지 않음, 재귀 호출 stack이 곧 트리의 path).

---

## 3. 직관과 정의

### 3.1 한 줄 비유

> **"미로에서 막다른 길 만나면 갈림길로 돌아가서 다른 갈래를 시도한다. 단, 갈림길로 돌아갈 때 들고 있던 표식을 회수한다."**

표식 회수 = **상태 되돌리기 (undo)**. 이게 빠지면 다음 가지가 오염된다.

### 3.2 정확한 정의

백트래킹은 다음을 만족하는 탐색 알고리즘:

1. **partial solution을 점진적으로 구성** — path에 한 원소씩 추가.
2. **각 단계에서 제약을 검사** — 위반 시 그 가지 포기 (pruning).
3. **leaf에 도달하면 결과 기록**.
4. **재귀 호출 후 상태를 정확히 원복** — 다음 형제 가지가 영향 받지 않도록.

### 3.3 brute force vs 백트래킹

```
brute force: 모든 조합 N! 개 생성 → 각각 검증
   비용: O(N! × validation)

backtracking: 부분 해 구성 중 무효면 즉시 abort
   비용: O(유효한 path 수 × N)
   pruning이 강하면 N!의 수십~수천분의 1
```

**예**: N-Queen N=8 brute force = 8^8 = 1670만. 백트래킹 = 약 15.7K 노드 (1000배 빠름).

### 3.4 중복 처리 핵심 — 정렬 + skip

같은 값 입력에서 같은 결과가 여러 가지에서 나오는 문제 (Permutations II, Combination Sum II, Subsets II).

```
[1, 1, 2] 순열
   naive: [1,1,2], [1,1,2] (첫 1과 둘째 1을 따로 보면 중복)

   해결: 정렬 + "같은 레벨에서 같은 값 skip"
        if (i > start && nums[i] == nums[i-1] && !used[i-1]) continue;
        ──────────────────────────────────────────────────
        같은 레벨에서 직전 형제와 값이 같고,
        그 형제가 이번 path에 안 쓰였다면 → 이미 그 경로를 본 적 있음

   결과: [1,1,2], [1,2,1], [2,1,1]  (중복 제거)
```

**핵심**: `!used[i-1]` = 같은 **레벨(같은 부모의 자식들 사이)**에서 중복 차단. `used[i-1]`이 true이면 다른 레벨(이전 형제가 path에 살아있음)이라 OK.

---

## 4. Java 템플릿

### 4.1 Permutations (순열, used[] 패턴) — LeetCode 46

```java
class Solution {
    public List<List<Integer>> permute(int[] nums) {
        List<List<Integer>> result = new ArrayList<>();
        boolean[] used = new boolean[nums.length];
        backtrack(nums, new ArrayList<>(), used, result);
        return result;
    }

    private void backtrack(int[] nums, List<Integer> path,
                           boolean[] used, List<List<Integer>> result) {
        // base case
        if (path.size() == nums.length) {
            result.add(new ArrayList<>(path));  // ★ 반드시 복사
            return;
        }
        for (int i = 0; i < nums.length; i++) {
            if (used[i]) continue;

            // 1. choose
            path.add(nums[i]);
            used[i] = true;

            // 2. explore
            backtrack(nums, path, used, result);

            // 3. unchoose (undo)
            path.remove(path.size() - 1);
            used[i] = false;
        }
    }
}
```

**암기 포인트**:
- `result.add(new ArrayList<>(path))` — path 자체를 넣으면 같은 ref라 끝에 비어버림.
- `path.remove(path.size() - 1)` — `ArrayList.remove(int)`는 index 기반, last 제거.
- used[i] = true/false 쌍이 정확히 맞물려야 함.

### 4.2 Permutations II (중복 처리) — LeetCode 47

```java
class Solution {
    public List<List<Integer>> permuteUnique(int[] nums) {
        Arrays.sort(nums);  // ★ 정렬이 핵심
        List<List<Integer>> result = new ArrayList<>();
        boolean[] used = new boolean[nums.length];
        backtrack(nums, new ArrayList<>(), used, result);
        return result;
    }

    private void backtrack(int[] nums, List<Integer> path,
                           boolean[] used, List<List<Integer>> result) {
        if (path.size() == nums.length) {
            result.add(new ArrayList<>(path));
            return;
        }
        for (int i = 0; i < nums.length; i++) {
            if (used[i]) continue;
            // ★ 같은 레벨에서 중복 skip
            if (i > 0 && nums[i] == nums[i - 1] && !used[i - 1]) continue;

            path.add(nums[i]);
            used[i] = true;
            backtrack(nums, path, used, result);
            path.remove(path.size() - 1);
            used[i] = false;
        }
    }
}
```

### 4.3 Subsets (부분집합) — LeetCode 78

```java
class Solution {
    public List<List<Integer>> subsets(int[] nums) {
        List<List<Integer>> result = new ArrayList<>();
        backtrack(nums, 0, new ArrayList<>(), result);
        return result;
    }

    private void backtrack(int[] nums, int start, List<Integer> path,
                           List<List<Integer>> result) {
        // ★ 모든 노드가 결과 (base case 없음, 매 호출이 결과)
        result.add(new ArrayList<>(path));
        for (int i = start; i < nums.length; i++) {
            path.add(nums[i]);
            backtrack(nums, i + 1, path, result);  // i+1: 이전 원소 안 봄
            path.remove(path.size() - 1);
        }
    }
}
```

**왜 start 패턴인가**: 조합/부분집합은 `{1,2}`와 `{2,1}`이 같음. 항상 오름차순 인덱스로만 가서 중복 방지.

### 4.4 Combinations (nCk) — LeetCode 77

```java
class Solution {
    public List<List<Integer>> combine(int n, int k) {
        List<List<Integer>> result = new ArrayList<>();
        backtrack(1, n, k, new ArrayList<>(), result);
        return result;
    }

    private void backtrack(int start, int n, int k, List<Integer> path,
                           List<List<Integer>> result) {
        if (path.size() == k) {
            result.add(new ArrayList<>(path));
            return;
        }
        // ★ pruning: 남은 자리 + 현재 위치가 n 넘으면 채울 수 없음
        // 남은 자리 = k - path.size()
        // 마지막 후보 인덱스 = n - (k - path.size()) + 1
        for (int i = start; i <= n - (k - path.size()) + 1; i++) {
            path.add(i);
            backtrack(i + 1, n, k, path, result);
            path.remove(path.size() - 1);
        }
    }
}
```

**Pruning trick**: `i <= n - (k - path.size()) + 1`. 남은 자리를 다 채울 수 있는 i까지만. 이걸 빼면 brute force, 넣으면 수십 배 빠름.

### 4.5 Combination Sum (중복 허용) — LeetCode 39

```java
class Solution {
    public List<List<Integer>> combinationSum(int[] candidates, int target) {
        Arrays.sort(candidates);  // pruning 위해 정렬
        List<List<Integer>> result = new ArrayList<>();
        backtrack(candidates, target, 0, new ArrayList<>(), result);
        return result;
    }

    private void backtrack(int[] cand, int remain, int start,
                           List<Integer> path, List<List<Integer>> result) {
        if (remain == 0) {
            result.add(new ArrayList<>(path));
            return;
        }
        for (int i = start; i < cand.length; i++) {
            if (cand[i] > remain) break;  // ★ 정렬되어 있으니 이후도 다 큼 → break
            path.add(cand[i]);
            // ★ i (i+1 아님): 같은 원소 중복 허용
            backtrack(cand, remain - cand[i], i, path, result);
            path.remove(path.size() - 1);
        }
    }
}
```

**핵심 차이**: 재귀 호출에 `i` 그대로 (Combinations는 `i+1`). 같은 인덱스 다시 쓸 수 있어서 중복 허용.

### 4.6 N-Queens — LeetCode 51

```java
class Solution {
    public List<List<String>> solveNQueens(int n) {
        List<List<String>> result = new ArrayList<>();
        int[] cols = new int[n];  // cols[row] = column of queen
        boolean[] colUsed = new boolean[n];
        boolean[] diag1 = new boolean[2 * n];  // row - col + n
        boolean[] diag2 = new boolean[2 * n];  // row + col
        backtrack(0, n, cols, colUsed, diag1, diag2, result);
        return result;
    }

    private void backtrack(int row, int n, int[] cols,
                           boolean[] colUsed, boolean[] diag1, boolean[] diag2,
                           List<List<String>> result) {
        if (row == n) {
            result.add(build(cols, n));
            return;
        }
        for (int col = 0; col < n; col++) {
            int d1 = row - col + n, d2 = row + col;
            if (colUsed[col] || diag1[d1] || diag2[d2]) continue;  // pruning

            cols[row] = col;
            colUsed[col] = true; diag1[d1] = true; diag2[d2] = true;

            backtrack(row + 1, n, cols, colUsed, diag1, diag2, result);

            colUsed[col] = false; diag1[d1] = false; diag2[d2] = false;
        }
    }

    private List<String> build(int[] cols, int n) {
        List<String> board = new ArrayList<>();
        for (int r = 0; r < n; r++) {
            char[] row = new char[n];
            Arrays.fill(row, '.');
            row[cols[r]] = 'Q';
            board.add(new String(row));
        }
        return board;
    }
}
```

**핵심 트릭**: O(1) 충돌 검사. column·대각선 2종을 boolean 배열로. 대각선은 `row - col`이 일정한 anti-diagonal 한 종, `row + col`이 일정한 main-diagonal 한 종.

### 4.7 Word Search (그리드 백트래킹) — LeetCode 79

```java
class Solution {
    private static final int[][] DIRS = {{-1,0},{1,0},{0,-1},{0,1}};

    public boolean exist(char[][] board, String word) {
        int m = board.length, n = board[0].length;
        for (int r = 0; r < m; r++)
            for (int c = 0; c < n; c++)
                if (board[r][c] == word.charAt(0) && dfs(board, r, c, word, 0))
                    return true;
        return false;
    }

    private boolean dfs(char[][] board, int r, int c, String word, int idx) {
        if (idx == word.length()) return true;
        if (r < 0 || r >= board.length || c < 0 || c >= board[0].length) return false;
        if (board[r][c] != word.charAt(idx)) return false;

        char save = board[r][c];
        board[r][c] = '#';  // ★ in-place visit 표시 (별도 visited 배열 절약)

        for (int[] d : DIRS) {
            if (dfs(board, r + d[0], c + d[1], word, idx + 1)) {
                board[r][c] = save;  // ★ unchoose (early return에서도 복원!)
                return true;
            }
        }

        board[r][c] = save;  // ★ unchoose
        return false;
    }
}
```

**트릭**: visited 배열 대신 board 자체에 `'#'` 표시. 메모리 절약 + cache locality. early return 직전에도 복원해야 함 (안 그러면 다음 starting cell에서 오염).

### 4.8 Generate Parentheses — LeetCode 22

```java
class Solution {
    public List<String> generateParenthesis(int n) {
        List<String> result = new ArrayList<>();
        backtrack(new StringBuilder(), 0, 0, n, result);
        return result;
    }

    private void backtrack(StringBuilder sb, int open, int close, int n,
                           List<String> result) {
        if (sb.length() == 2 * n) {
            result.add(sb.toString());
            return;
        }
        if (open < n) {  // pruning: open 더 쓸 수 있을 때만
            sb.append('(');
            backtrack(sb, open + 1, close, n, result);
            sb.deleteCharAt(sb.length() - 1);
        }
        if (close < open) {  // pruning: close가 open 못 넘음
            sb.append(')');
            backtrack(sb, open, close + 1, n, result);
            sb.deleteCharAt(sb.length() - 1);
        }
    }
}
```

**Pruning의 위력**: 무조건 두 갈래 전부 시도하면 2^(2n), pruning으로 카탈란 수 C_n = `(1/(n+1)) * C(2n, n)` ≈ 4^n/n^1.5. n=10이면 16384 vs 16796 — 카탈란이 4배 작음. n이 클수록 격차 커짐.

---

## 5. Kotlin 템플릿

### 5.1 Permutations

```kotlin
class Solution {
    fun permute(nums: IntArray): List<List<Int>> {
        val result = mutableListOf<List<Int>>()
        val used = BooleanArray(nums.size)
        backtrack(nums, mutableListOf(), used, result)
        return result
    }

    private fun backtrack(nums: IntArray, path: MutableList<Int>,
                          used: BooleanArray, result: MutableList<List<Int>>) {
        if (path.size == nums.size) {
            result.add(path.toList())  // ★ toList()로 복사
            return
        }
        for (i in nums.indices) {
            if (used[i]) continue
            path.add(nums[i]); used[i] = true
            backtrack(nums, path, used, result)
            path.removeAt(path.size - 1); used[i] = false
        }
    }
}
```

### 5.2 Permutations II (중복)

```kotlin
fun permuteUnique(nums: IntArray): List<List<Int>> {
    nums.sort()
    val result = mutableListOf<List<Int>>()
    val used = BooleanArray(nums.size)
    fun bt(path: MutableList<Int>) {
        if (path.size == nums.size) { result.add(path.toList()); return }
        for (i in nums.indices) {
            if (used[i]) continue
            if (i > 0 && nums[i] == nums[i-1] && !used[i-1]) continue
            path.add(nums[i]); used[i] = true
            bt(path)
            path.removeAt(path.size - 1); used[i] = false
        }
    }
    bt(mutableListOf())
    return result
}
```

Kotlin local function으로 클로저 캡처 — 파라미터 전달 줄임.

### 5.3 Subsets

```kotlin
fun subsets(nums: IntArray): List<List<Int>> {
    val result = mutableListOf<List<Int>>()
    fun bt(start: Int, path: MutableList<Int>) {
        result.add(path.toList())
        for (i in start until nums.size) {
            path.add(nums[i])
            bt(i + 1, path)
            path.removeAt(path.size - 1)
        }
    }
    bt(0, mutableListOf())
    return result
}
```

### 5.4 Combinations

```kotlin
fun combine(n: Int, k: Int): List<List<Int>> {
    val result = mutableListOf<List<Int>>()
    fun bt(start: Int, path: MutableList<Int>) {
        if (path.size == k) { result.add(path.toList()); return }
        for (i in start..(n - (k - path.size) + 1)) {
            path.add(i)
            bt(i + 1, path)
            path.removeAt(path.size - 1)
        }
    }
    bt(1, mutableListOf())
    return result
}
```

### 5.5 Combination Sum

```kotlin
fun combinationSum(candidates: IntArray, target: Int): List<List<Int>> {
    candidates.sort()
    val result = mutableListOf<List<Int>>()
    fun bt(start: Int, remain: Int, path: MutableList<Int>) {
        if (remain == 0) { result.add(path.toList()); return }
        for (i in start until candidates.size) {
            if (candidates[i] > remain) break
            path.add(candidates[i])
            bt(i, remain - candidates[i], path)
            path.removeAt(path.size - 1)
        }
    }
    bt(0, target, mutableListOf())
    return result
}
```

### 5.6 N-Queens

```kotlin
fun solveNQueens(n: Int): List<List<String>> {
    val result = mutableListOf<List<String>>()
    val cols = IntArray(n)
    val colUsed = BooleanArray(n)
    val diag1 = BooleanArray(2 * n)
    val diag2 = BooleanArray(2 * n)

    fun build(): List<String> = (0 until n).map { r ->
        CharArray(n) { c -> if (c == cols[r]) 'Q' else '.' }.concatToString()
    }

    fun bt(row: Int) {
        if (row == n) { result.add(build()); return }
        for (col in 0 until n) {
            val d1 = row - col + n; val d2 = row + col
            if (colUsed[col] || diag1[d1] || diag2[d2]) continue
            cols[row] = col
            colUsed[col] = true; diag1[d1] = true; diag2[d2] = true
            bt(row + 1)
            colUsed[col] = false; diag1[d1] = false; diag2[d2] = false
        }
    }
    bt(0)
    return result
}
```

### 5.7 Word Search

```kotlin
fun exist(board: Array<CharArray>, word: String): Boolean {
    val m = board.size; val n = board[0].size
    val dirs = arrayOf(intArrayOf(-1,0), intArrayOf(1,0),
                       intArrayOf(0,-1), intArrayOf(0,1))

    fun dfs(r: Int, c: Int, idx: Int): Boolean {
        if (idx == word.length) return true
        if (r !in 0 until m || c !in 0 until n) return false
        if (board[r][c] != word[idx]) return false

        val save = board[r][c]
        board[r][c] = '#'
        for (d in dirs) {
            if (dfs(r + d[0], c + d[1], idx + 1)) {
                board[r][c] = save
                return true
            }
        }
        board[r][c] = save
        return false
    }

    for (r in 0 until m)
        for (c in 0 until n)
            if (board[r][c] == word[0] && dfs(r, c, 0)) return true
    return false
}
```

### 5.8 Generate Parentheses

```kotlin
fun generateParenthesis(n: Int): List<String> {
    val result = mutableListOf<String>()
    val sb = StringBuilder()
    fun bt(open: Int, close: Int) {
        if (sb.length == 2 * n) { result.add(sb.toString()); return }
        if (open < n) {
            sb.append('('); bt(open + 1, close); sb.deleteCharAt(sb.length - 1)
        }
        if (close < open) {
            sb.append(')'); bt(open, close + 1); sb.deleteCharAt(sb.length - 1)
        }
    }
    bt(0, 0)
    return result
}
```

---

## 6. 시간/공간 복잡도

### 6.1 일반 식

```
T(n) = (branching factor)^(depth) × (each node work)
     = b^d × O(n)         // path copy 또는 valid check
```

| 문제 | branching | depth | 노드 수 | leaf 결과 복사 | 총 시간 |
|---|---|---|---|---|---|
| Permutations | n→n-1→...→1 | n | n! | O(n) | **O(n × n!)** |
| Subsets | 2 (include or not) | n | 2^n | O(n) | **O(n × 2^n)** |
| Combinations nCk | ≤ n | k | C(n,k) | O(k) | **O(k × C(n,k))** |
| Combination Sum (target T, min cand m) | ≤ n | T/m | 지수 (입력 의존) | O(T/m) | **O(n^(T/m))** 상한 |
| N-Queens | ≤ n | n | pruning 후 ~O(n!) 작음 | O(n²) | **O(n!)** 상한, 실제 훨씬 작음 |
| Word Search | 4 (방향) | len(word) | 4^L | O(L) | **O(m·n·4^L)** |
| Generate Parens | ≤ 2 | 2n | 카탈란 C_n | O(n) | **O(n × C_n) = O(4^n / √n)** |

### 6.2 공간

- **재귀 스택**: O(depth) = 문제 길이에 비례.
- **path / used[] / visited**: O(n).
- **결과 자체**: 결과 수에 비례 (지수). LeetCode는 보통 결과 공간을 시간 분석에 포함시키지 않음.

### 6.3 Pruning의 실제 효과

```
N-Queen 노드 수 (search tree size)
  N=4:  대략 17 (brute 256)
  N=8:  대략 15,720 (brute 16M, 약 1000배)
  N=12: 대략 856M (brute 1조)
```

Pruning은 점근적 차수를 안 줄여도 (worst case는 같을 수 있음) 실측 상수를 크게 낮춤. **DP로 변환 가능한가**를 늘 검토 — 중복 부분 문제가 있으면 백트래킹 자체가 비효율.

### 6.4 재귀 깊이 함정

- Java 기본 stack: 약 512KB → 깊이 1만 즈음에서 StackOverflow.
- N=20 순열: depth 20, 문제 없음.
- 격자 m×n=1000×1000 미로 깊이는 1M → StackOverflow 위험.
- 대응: iterative + explicit stack, 또는 `-Xss4m`으로 stack 키우기.

---

## 7. 대표 문제 풀이 — 7개

### 7.1 LeetCode 46 — Permutations

**요약**: 서로 다른 정수 배열의 모든 순열.

**입력**: `[1,2,3]` → **출력**: `[[1,2,3],[1,3,2],[2,1,3],[2,3,1],[3,1,2],[3,2,1]]`.

**접근**: used[] 패턴. 매 단계에서 안 쓴 모든 원소 시도.

**Java**: (§4.1 템플릿 그대로)

**Kotlin**: (§5.1 그대로)

**복잡도**: O(n × n!). n=10이면 36M, n=12면 5.7B → n ≤ 10이 입력 한계.

**함정**:
- `result.add(path)`만 하면 같은 객체 ref라 마지막에 다 비어버림 → `new ArrayList<>(path)`.
- used[i] = false 빼먹으면 첫 가지만 정상, 형제 가지에서 그 원소 영영 못 씀.

### 7.2 LeetCode 47 — Permutations II

**요약**: 중복 원소 있는 배열의 unique 순열.

**입력**: `[1,1,2]` → **출력**: `[[1,1,2],[1,2,1],[2,1,1]]`.

**접근**: 정렬 + 같은 레벨 같은 값 skip. 핵심 조건은 `!used[i-1]`.

**왜 `!used[i-1]`인가?**

```
[1, 1, 2] 정렬됨, i=0과 i=1이 동값 (둘 다 1)
  
  Case A: i=0 (첫 1) 선택 후 → 다음 레벨에서 i=1 (둘째 1) 선택
       used[0]=true, used[1]=false였다가 사용
       → 정상적인 [1, 1, ...] 진행
       
  Case B: i=0 (첫 1) skip 후 → 같은 레벨에서 i=1 (둘째 1) 선택
       used[0]=false인 상태에서 nums[1]==nums[0]이면
       → "첫 1을 안 쓰고 둘째 1만 쓰는" 분기 = 어차피 동값이라 같은 결과
       → skip
       
  → 조건: i > 0 && nums[i] == nums[i-1] && !used[i-1]
                                              ↑
                                          같은 레벨 형제 중복 차단
```

**Java**: (§4.2 그대로)

**복잡도**: O(n × n!) worst case, 중복 많으면 더 빠름.

**함정**: 정렬 잊으면 skip 조건이 동작 안 함. `Arrays.sort(nums)` 필수.

### 7.3 LeetCode 78 — Subsets

**요약**: 모든 부분집합 (power set, 2^n개).

**입력**: `[1,2,3]` → **출력**: `[[], [1], [1,2], [1,2,3], [1,3], [2], [2,3], [3]]`.

**접근 2가지**:

**(1) Backtracking — 시작 인덱스**: (§4.3 템플릿)

**(2) Bitmask 반복**:

```java
public List<List<Integer>> subsets(int[] nums) {
    int n = nums.length;
    List<List<Integer>> result = new ArrayList<>();
    for (int mask = 0; mask < (1 << n); mask++) {
        List<Integer> subset = new ArrayList<>();
        for (int i = 0; i < n; i++)
            if ((mask & (1 << i)) != 0) subset.add(nums[i]);
        result.add(subset);
    }
    return result;
}
```

n ≤ 20이면 bitmask가 간결. n ≥ 30이면 mask가 int 범위 넘어가 위험.

**복잡도**: O(n × 2^n).

**함정**: base case 따로 안 둠 — 매 호출이 결과 (빈 [] 포함). 결과 누락하면 빈 집합 못 잡음.

### 7.4 LeetCode 51 — N-Queens

**요약**: n×n 보드에 n개 queen을 서로 공격 안 하게 배치하는 모든 방법.

**입력**: `n=4` → **출력**: 2개 (`[[".Q..","...Q","Q...","..Q."], ...]`).

**접근**: 한 row에 정확히 1개 queen, column·대각선 충돌 검사. row 단위 결정 트리.

**Java**: (§4.6 그대로)

**복잡도**:
- 상한: `n × n × ... × n` = O(n^n) — 모든 cell 시도.
- 실측: n=8 → 약 1만 노드, n=12 → 약 1M (pruning 효과 1000~10000배).

**함정**:
- 대각선 인덱스 음수 처리 — `row - col + n`로 0 이상 보장.
- 작은 N부터 brute force와 비교해 검증 (N=4 → 2개, N=8 → 92개).

**시니어 매핑**: 이게 **constraint satisfaction (CSP)**의 교과서 예. SAT solver, Sudoku solver, scheduler가 같은 구조 — variable, domain, constraint. Java JIT의 register allocator도 graph coloring + backtracking.

### 7.5 LeetCode 79 — Word Search

**요약**: 그리드에서 인접 셀(상하좌우)을 따라 단어를 만들 수 있는지. 같은 셀 두 번 못 씀.

**입력**: 그리드 + `"ABCCED"` → **출력**: true.

**접근**: 모든 시작 셀에서 DFS, in-place visited 표시.

**Java**: (§4.7 그대로)

**복잡도**: O(m × n × 4^L), L = word.length. 실제로는 첫 문자 일치 시작 후보가 적고 pruning 강해서 훨씬 빠름.

**함정**:
- visited 복원 빼먹으면 다른 시작 셀에서 부정확.
- 첫 문자 빠른 검사로 시작 셀 후보 줄이기 (자주 빠뜨림).
- early return 직전에도 복원 — `if (dfs(...)) { board[r][c] = save; return true; }`.

**최적화**: word의 첫·마지막 문자 빈도가 적은 쪽부터 시작. Trie 쓰면 Word Search II (다중 word) 가능.

### 7.6 LeetCode 22 — Generate Parentheses

**요약**: 유효한 괄호 n쌍의 모든 조합.

**입력**: `n=3` → **출력**: `["((()))","(()())","(())()","()(())","()()()"]`.

**접근**: open ≤ n, close ≤ open 두 제약. 위반은 즉시 pruning.

**Java**: (§4.8 그대로)

**복잡도**: 결과 수 = 카탈란 수 C_n = `(1/(n+1)) × C(2n, n)`.

```
n:    1  2  3   4   5    6    7    8     9     10
C_n:  1  2  5  14  42  132  429 1430  4862  16796
```

**함정**:
- "open과 close가 같으면 끝" 조건만 보면 `)(`도 통과. **close < open 조건 필수**.
- 결과 검증 후 add 방식은 brute force (4^n 노드), pruning 백트래킹은 카탈란 노드만 방문.

**시니어 매핑**: 카탈란 수 — 이진 트리 모양 수, lattice path 수, polygon triangulation 수와 같은 수열. DP·combinatorics 단골.

### 7.7 LeetCode 17 — Letter Combinations of a Phone Number

**요약**: 폰 키패드 숫자 문자열 → 만들 수 있는 모든 알파벳 문자열.

**입력**: `"23"` → **출력**: `["ad","ae","af","bd","be","bf","cd","ce","cf"]`.

**Java**:

```java
class Solution {
    private static final String[] MAP = {
        "", "", "abc", "def", "ghi", "jkl",
        "mno", "pqrs", "tuv", "wxyz"
    };

    public List<String> letterCombinations(String digits) {
        List<String> result = new ArrayList<>();
        if (digits.isEmpty()) return result;
        backtrack(digits, 0, new StringBuilder(), result);
        return result;
    }

    private void backtrack(String digits, int idx, StringBuilder sb,
                           List<String> result) {
        if (idx == digits.length()) {
            result.add(sb.toString());
            return;
        }
        String letters = MAP[digits.charAt(idx) - '0'];
        for (char c : letters.toCharArray()) {
            sb.append(c);
            backtrack(digits, idx + 1, sb, result);
            sb.deleteCharAt(sb.length() - 1);
        }
    }
}
```

**Kotlin**:

```kotlin
fun letterCombinations(digits: String): List<String> {
    if (digits.isEmpty()) return emptyList()
    val map = arrayOf("", "", "abc", "def", "ghi", "jkl",
                      "mno", "pqrs", "tuv", "wxyz")
    val result = mutableListOf<String>()
    val sb = StringBuilder()
    fun bt(idx: Int) {
        if (idx == digits.length) { result.add(sb.toString()); return }
        for (c in map[digits[idx] - '0']) {
            sb.append(c); bt(idx + 1); sb.deleteCharAt(sb.length - 1)
        }
    }
    bt(0)
    return result
}
```

**복잡도**: O(4^n × n), n = digits.length (4는 7/9의 letter 수).

**함정**:
- 빈 입력 — `return emptyList()` (안 하면 `[""]` 한 개 리턴).
- StringBuilder vs 새 String concat — 후자는 매 호출 O(n) 복사라 4^n × n² 됨.

---

## 8. 함정·엣지케이스

### 8.1 결과 리스트 복사 빼먹기 — 1순위 함정

```java
// ✘ 틀림 — path는 한 객체, 끝나면 빈 상태로 다 비어버림
result.add(path);

// ✓ 정답 — 매 결과는 독립 스냅샷
result.add(new ArrayList<>(path));
```

**왜?** path는 backtrack 도중 계속 변동. 모든 result entry가 같은 ArrayList ref를 가리키면 마지막에 다 같은 (보통 빈) 리스트가 됨.

**Kotlin**: `path.toList()` (`toMutableList()` 아님 — 새 unmodifiable copy면 충분).

### 8.2 used[] / visited 되돌리기 누락 — 2순위 함정

```java
for (...) {
    used[i] = true;
    backtrack(...);
    // used[i] = false;  ← 빼먹으면?
}
```

첫 가지만 정상, 형제 가지는 이전 used[]가 살아있어 후보 누락. 디버깅 신호: 결과 수가 비정상적으로 적음.

**Word Search**: early return 분기에서도 복원해야 함. `if (dfs(...)) { board[r][c] = save; return true; }`.

### 8.3 중복 입력 정렬 빼먹기

```java
// Permutations II / Combination Sum II
// ✘ Arrays.sort(nums) 빼먹음
// 결과: 같은 값이 인접 안 해서 skip 조건 무력화 → 중복 결과
```

`if (i > 0 && nums[i] == nums[i-1] && !used[i-1]) continue;` 조건이 작동하려면 동값이 인접해야 한다.

### 8.4 base case 위치

```java
// Subsets: 매 호출이 결과
void bt(int start, List<Integer> path) {
    result.add(new ArrayList<>(path));   // ★ 호출 시작에
    for (int i = start; i < n; i++) { ... }
}

// Permutations: leaf만 결과
void bt(...) {
    if (path.size() == n) {
        result.add(new ArrayList<>(path));   // ★ leaf 도달 시만
        return;
    }
    for (int i = 0; i < n; i++) { ... }
}
```

Subsets 같이 모든 노드 결과인 문제에서 leaf 조건 두면 빈 집합 누락. 반대로 Permutations에서 매 호출 추가하면 partial path가 결과에 섞임.

### 8.5 in-place 변형 후 복원 실수 — Word Search 류

```java
board[r][c] = '#';     // 표시
for (...) { dfs(...) }
board[r][c] = save;    // 복원

// ✘ 예외 던지면 복원 안 됨 → try-finally 필요?
// 보통 보드 문제는 예외 없으니 단순 복원으로 충분
// 단, 재귀 안에서 early return 분기마다 복원 챙겨야
```

### 8.6 빈 입력 / 단일 원소

| 문제 | 빈 입력 | 단일 원소 |
|---|---|---|
| Subsets `[]` | `[[]]` | `[[], [a]]` |
| Permutations `[]` | `[[]]` | `[[a]]` |
| Letter Combos `""` | `[]` (빈 리스트!) | 키패드 문자 수 만큼 |
| Combinations n=0,k=0 | `[[]]` | 문제별 정의 확인 |

특히 Letter Combinations의 `digits=""` 케이스를 명시 처리 안 하면 빈 문자열 1개 든 결과가 나옴 — 문제 정의에 따라 틀림.

### 8.7 재귀 깊이 / Stack Overflow

격자 1000×1000 미로의 백트래킹은 최악 깊이 1M → `java.lang.StackOverflowError`. 대응:
- iterative + explicit `ArrayDeque<int[]>` stack.
- JVM 옵션 `-Xss8m` (코딩 테스트 환경에선 어려움).
- 보통 LeetCode/프로그래머스 입력 크기는 안전 범위.

---

## 9. 꼬리질문 트리 — 면접관이 던질 질문 미리 답변

### Q1. "Pruning을 더 강하게 할 수 있나요?"

> **3종류로 분류해서 답한다**:
> 1. **infeasibility pruning** — 제약 위반 즉시 컷. N-Queen 대각선이 그 예.
> 2. **bound pruning** — 현재 누적이 한계 넘으면 컷. Combination Sum에서 `cand[i] > remain` break (sort 후).
> 3. **symmetry pruning** — 대칭 해 제거. N-Queen 첫 row를 0..N/2만 봐서 2배 절감.
>
> 추가로 **branch ordering** — 분기 순서 조정. 가장 제약 강한 (도메인 작은) 변수부터 — Sudoku에서 빈칸 중 후보 수 적은 것부터 시도하면 search tree 급감 (MRV heuristic).

### Q2. "이 문제 Memoization으로 DP 전환 가능한가요?"

> **중복 부분 문제가 있는지 본다**:
> - **Permutations** — `[1,2,3]` 순열에서 `(used={1,2}, 남은=3)` 상태가 여러 번? 한 번. → DP 불가, 백트래킹이 최적.
> - **Combination Sum** — `(start, remain)` 상태가 여러 가지에서 등장? 가능. **memo[start][remain]**으로 DP 변환 가능 (단, 답이 "방법 수"일 때).
> - **Word Break** — 같은 시작 위치의 후속 분할이 반복됨 → DP 명백히 효과적.
>
> **백트래킹이 "모든 해를 나열"이면 DP 무리**. 답 자체가 지수 개라 시간 하한이 지수. DP는 "개수/최적값"처럼 한 값으로 압축 가능할 때.

### Q3. "Branch and Bound와 백트래킹 차이는?"

> **백트래킹**: 모든 유효 해 탐색 (또는 1개 해). pruning은 "infeasible" 위주.
> **Branch and Bound**: 최적화 문제 전용. 현재 best 답을 들고 다니며, "이 가지로 가도 best 못 깬다"가 증명되면 컷 (bound pruning).
>
> 예: TSP 외판원. 백트래킹으로 모든 순환 시도 가능하지만, 각 노드에서 "현재 누적 + lower bound > 현재 best"면 컷 → branch and bound. ILP solver (Gurobi/CPLEX)의 핵심 알고리즘. **Branch and Bound ⊂ 백트래킹의 최적화 특화 버전**.

### Q4. "비트마스크로 used[]를 대체할 수 있나요?"

> n ≤ 20이면 가능. `int used` 또는 `long used` 한 값으로 압축.
> - `used & (1 << i)` → i번째 사용 여부.
> - `used | (1 << i)` → set, `used & ~(1 << i)` → unset.
>
> **이점**:
> - 메모리 1/32 (boolean 배열 32 byte → int 4 byte).
> - cache locality 극대 (1 word).
> - state로 키 삼아 memoization 가능 → **bitmask DP**로 자연스럽게 발전.
>
> **예**: TSP `dp[mask][last]` = `mask`까지 방문, 마지막 도시 `last`일 때 최소 비용. N=20에서 백트래킹은 20! ≈ 2.4 × 10^18 불가능, bitmask DP는 2^20 × 20 = 2천만 가능.

### Q5. "재귀 없이 iterative로?"

> 가능. 명시 stack에 (state, choice index) push. 다만 코드가 장황해지고 디버깅 어려움.
> 실전: stack overflow 위험이 있을 때만 (격자 큼/깊이 깊음). 코딩 테스트는 거의 항상 재귀가 가독성 승리.

### Q6. "결과 개수만 필요한 N-Queen에서 더 빠른 방법?"

> 1. **비트마스크** (위 7.8) — boolean 3개 → int 3개. 후보 산출 한 번에.
> 2. **대칭** — 첫 row 0..N/2만 보고 결과 2배 (홀수 N의 중앙은 별도).
> 3. **공지된 결과 table** — N ≤ 27까지 OEIS A000170에 있음. 면접에선 답 안 됨.

### Q7. "스도쿠/N-Queen은 production에서 어디 쓰이나요?"

> 실제 스도쿠를 풀 일은 거의 없지만, 같은 알고리즘 구조가:
> - **DB query planner의 join order 탐색** — n개 테이블 join, n!개 순열에서 cost 최소. PostgreSQL `geqo_threshold`는 n=12부터 백트래킹 대신 유전 알고리즘으로 전환 (Postgres default).
> - **SAT solver (DPLL/CDCL)** — Boolean variable 할당 트리, unit propagation으로 pruning. Z3, MiniSAT.
> - **Constraint satisfaction (Scheduler)** — Airbnb/Google 회의실 스케줄러, container bin-packing.
> - **JIT register allocation** — graph coloring, 변수 → 레지스터 할당.
> - **OR-Tools (Google)** — CSP solver. 노선 최적화, factory scheduling.

### Q8. "함수형 스타일 (Stream/Sequence)로 백트래킹?"

> 가능은 하지만 권장 X. mutable state(path, used)가 본질이라 functional은 매 단계마다 새 List 생성 → 메모리/시간 손해. 백트래킹은 mutation + undo가 본질.
>
> 단, **leetcode trick**으로 `path.add(...).also { result.add(it.toList()) }` 같은 콤보는 가독성 좋음. 본질은 그대로.

---

## 10. 다른 패턴과의 연결

### 10.1 DFS의 일반화

```
DFS (그래프/트리):
   visited 표시 → 인접 노드 재귀 → return
   (보통 visited 복원 안 함 — 같은 노드 재방문 금지)

백트래킹:
   choose → 재귀 → unchoose
   (상태 복원이 핵심 — 다른 path에서 같은 원소 재사용 가능)
```

**Word Search**가 정확히 둘의 경계. 같은 path 내에서는 셀 재방문 금지 (visited), 다른 path에서는 재방문 가능 (unchoose). 그래서 DFS이자 백트래킹.

### 10.2 DP로의 전환

**전환 조건**: 같은 (sub-state)가 여러 path에서 등장 (overlapping subproblems).

| 문제 | 백트래킹 | DP 가능? |
|---|---|---|
| Permutations (모든 순열 나열) | O(n!) | ✘ 결과 자체가 n!개 |
| "n개 중 k개 합 = target 방법 수" | O(2^n) | ✓ dp[i][sum] O(n × target) |
| Word Break (분할 가능?) | O(2^n) | ✓ dp[i] O(n²) |
| Edit Distance | 재귀 O(3^max) | ✓ dp[i][j] O(mn) |
| LCS | 재귀 O(2^n) | ✓ dp[i][j] O(mn) |

**결정 기준**:
- 결과가 "개수/최적값" 한 스칼라 → DP 거의 확실.
- 결과가 "모든 유효한 해 나열" → 백트래킹 (DP 무리).

### 10.3 Bitmask DP로 확장

state가 "어떤 원소들 사용 중"이고 n ≤ 20:

```
TSP 백트래킹: O(n!) — n=20에서 불가
TSP bitmask DP: dp[mask][last] O(2^n × n²) — n=20에서 약 4 × 10^8, 가능
```

**Traveling Salesman**, **Set Cover**, **Hamiltonian Path**가 대표. 백트래킹 → bitmask DP는 "state = used[] 통째로"라는 발상.

### 10.4 Branch and Bound (최적화)

백트래킹의 최적화 버전. 현재 best를 들고 다니며 lower bound로 컷.

```
backtrack(state):
    if leaf: update best
    for choice in choices:
        if state.cost + lower_bound(remaining) >= best: continue  // ★ bound
        choose; recurse; unchoose
```

ILP (Integer Linear Programming) solver의 뼈대. TSP, Knapsack 변형, Vehicle Routing.

### 10.5 Iterative Deepening / IDA*

깊이 제한 두고 점차 늘리는 백트래킹. 게임 AI (체스 minimax + alpha-beta), 15-puzzle. 메모리 적게 쓰는 BFS 대안.

### 10.6 Constraint Propagation

스도쿠/N-Queen에서 한 선택의 영향을 즉시 다른 변수의 도메인에 전파 → search tree 더 작아짐. AC-3 알고리즘.

```
Sudoku에서 (1,1)에 5 둠
  → row 1, col 1, box (0~2)(0~2) 모든 빈칸의 후보에서 5 제거
  → 만약 어떤 빈칸 후보가 1개로 줄면 즉시 확정 (unit propagation)
  → 어떤 빈칸 후보가 0개면 즉시 backtrack
```

SAT solver의 핵심 기법. 백트래킹의 진화형.

---

## 11. 시니어 운영 매핑

### 11.1 DB Query Planner — Join Order 탐색

PostgreSQL/MySQL/Oracle의 optimizer가 n개 테이블 join 시:

```
join order = n!개 순열 (실제는 left-deep tree로 줄여도 n!)
   각 순서마다 cost (page read, hash build, sort, ...) 추정
   최소 cost 선택

n ≤ 12: 백트래킹 전수 탐색
n > 12: 휴리스틱 (PostgreSQL geqo = genetic algorithm)
```

**Postgres `geqo_threshold = 12` 기본값** — 12 테이블 이상이면 백트래킹 포기. 시니어가 explain plan 보고 "왜 이 join 순서?"를 이해하려면 백트래킹 + cost-based pruning을 알아야 한다.

### 11.2 SAT Solver — DPLL/CDCL

```
DPLL = Davis-Putnam-Logemann-Loveland (1962)
   Boolean variable 하나 true/false 선택 → 백트래킹
   + unit propagation (constraint 전파)
   + pure literal elimination

CDCL = Conflict-Driven Clause Learning (1996, GRASP)
   백트래킹 도중 conflict 만나면 "왜 이 conflict?" 분석
   학습된 clause 추가 → 같은 conflict 재발생 방지
   비-chronological backtrack (학습 점프)
```

MiniSAT, Z3, CryptoMiniSat 모두 이 기반. SMT solver는 SAT + theory solver. **type checker (Haskell GHC, Rust trait resolver)도 본질적으로 SAT/CSP**. 백트래킹이 컴파일러 깊은 곳에 있다.

### 11.3 Scheduler / Container Bin Packing

Kubernetes scheduler: pod를 node에 배치할 때 (resource, affinity, taint, topology spread) 제약을 모두 만족하는 배치 탐색. 큰 클러스터는 휴리스틱이지만 작은 cluster는 backtracking-like.

OR-Tools (Google), Hashicorp Nomad, Mesos: CSP 알고리즘 기반. Scheduling = variable assignment + constraint.

### 11.4 JIT Register Allocation

```
graph coloring problem:
   variable = node
   동시에 살아있는 변수 = edge
   목표: k색(=레지스터 수)으로 칠하기

Chaitin's algorithm: backtracking + spill heuristic
```

HotSpot C2, GraalVM, LLVM 모두 backtracking + heuristic. 컴파일 시간이 너무 길어지면 (lower) 폴백.

### 11.5 자동 추론 / Type Checker

```
Rust trait resolution:
   trait bound A: B + C에서 어떤 impl을 고르나
   여러 candidate → 백트래킹 + constraint propagation

Haskell type inference (Hindley-Milner + extensions):
   변수의 type을 unification으로 도출
   ambiguous → 백트래킹
```

`error: type annotations needed` 가 결국 백트래킹 실패 메시지.

### 11.6 운영 진단 — 백트래킹 패턴 코드 리뷰

| 증상 | 원인 후보 |
|---|---|
| 응답시간이 입력 크기에 폭발 | brute force (pruning 누락) |
| 입력 정렬 누락 → 중복 결과 | Permutations II 등 sort 빠뜨림 |
| StackOverflow | 깊이 제한, iterative 전환 |
| OOM 발생 (결과 리스트) | 결과 개수 자체가 지수 — 알고리즘 재선택 (DP, streaming) |
| 같은 결과 여러 번 | unchoose 누락 / 결과 복사 누락 |

### 11.7 마지막 한 마디

> 백트래킹은 단순히 "조합/순열 푸는 트릭"이 아니다.
> **암묵적 결정 트리 + DFS + pruning** — 이 본질이 join order, SAT, scheduling, register allocation, type inference, container packing에 모두 흐른다.
> 라이브 코딩에서 boilerplate 3줄(choose/recurse/unchoose)을 30초에 쓰는 것은 입문, **decision tree를 즉석에서 그리며 pruning 조건을 면접관과 함께 설계하는 것**이 마스터.

---

> 백트래킹이라는 단어를 들었을 때 머릿속에 자동으로 떠올라야 한다: decision tree + choose/recurse/unchoose 3단 + used[] vs start index 패턴 분기 + 중복 처리 (sort + skip) + pruning 3종 (infeasibility/bound/symmetry) + DFS 일반화 + DP/Bitmask DP/Branch and Bound로의 확장 + production의 query planner / SAT / scheduler 매핑. 이게 시니어가 백트래킹을 "안다"는 의미다.
