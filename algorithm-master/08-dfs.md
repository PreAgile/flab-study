# 08. DFS (Depth-First Search)

> "DFS? 재귀로 끝까지 들어가는 거"는 입문자.
> 마스터는 **재귀 호출 스택 = JVM 콜 스택**임을 알고, `visited`를 들어갈 때 마킹할지 빠질 때 마킹할지 구분하고, 무방향 그래프에서 부모 노드를 어떻게 거를지 즉답하고, 그래프 크기에 따라 iterative 변환을 선택한다. 그리고 production에서는 **디렉토리 walk, Spring DI 순환참조 검출, GC reachability marking**이 전부 DFS임을 본다.
>
> 이 문서는 "그리드 4방향 외우기" 대신 본질·왜·연결·운영 진단을 다룬다.

---

## 0. 목차

1. 인지 신호 — 30초 분류
2. 백지 그리기 — DFS의 시각화 9종
3. 직관과 정의 — 재귀, 스택, visited의 본질
4. Java 템플릿 — 4가지 변형
5. Kotlin 템플릿 — 4가지 변형
6. 시간/공간 복잡도 — V, E, R*C
7. 대표 문제 8개 — Java + Kotlin 풀이
8. 함정·엣지케이스 — StackOverflowError, visited 위치, 부모 재방문
9. 꼬리질문 트리
10. 다른 패턴과의 연결
11. 시니어 운영 연결 — 디렉토리 walk, DI 순환참조, GC marking

---

## 1. 인지 신호 — 30초 분류

문제 설명만 읽고 다음 신호가 보이면 DFS가 1차 후보다.

| 신호 | 예시 문제 |
|---|---|
| **"섬의 개수"**, "연결 컴포넌트 개수" | LeetCode 200 |
| **"가장 큰 영역"**, "최대 면적" | LeetCode 695 |
| **"모든 경로 탐색"**, "조합 합 = 타겟" | Programmers 타겟 넘버 |
| **"도달 가능 여부"**, "reachability" | LeetCode 417 |
| **"트리 깊이/지름/경로 합"** | LeetCode 104, 543, 124 |
| **"그래프 사이클 검출"**, "위상정렬" | LeetCode 207, 210 |
| **"네트워크 연결 컴포넌트"** | Programmers 네트워크 |
| **"backtracking 직전 단계"** | 순열·조합·N-Queen은 DFS + 되돌리기 |

DFS vs BFS 1차 분기:

- **최단 거리(간선 가중치 없음)** → BFS (DFS는 최단을 보장 안 함)
- **모든 경로/모든 영역/도달 가능** → DFS (간결, 메모리 적음)
- **레벨별 처리** → BFS
- **재귀가 자연스러운 트리/그래프 순회** → DFS

다른 패턴과 햇갈리지 말 것:

- "정렬된 배열에서 찾기" → Binary Search
- "구간 합" → Prefix Sum
- "연속 부분 배열" → Sliding Window
- "괄호/스택 매칭" → Stack
- "선택→되돌리기" → Backtracking (DFS의 한 갈래)

---

## 2. 백지 그리기 — DFS의 시각화 9종

### 2.1 트리 DFS — pre/in/post-order

```
        1
       / \
      2   3
     / \   \
    4   5   6

DFS 호출 순서 (재귀 진입 순서):
    1 → 2 → 4 → (back) → 5 → (back) → (back) → 3 → 6

Pre-order  (방문→왼→오): 1 2 4 5 3 6
In-order   (왼→방문→오): 4 2 5 1 3 6
Post-order (왼→오→방문): 4 5 2 6 3 1
```

언제 무엇을 쓰나?

- **pre-order**: 트리 복제, 직렬화 (parent를 먼저 알아야 child 알 수 있을 때)
- **in-order**: BST → 정렬된 순회
- **post-order**: 자식 결과를 모아 부모 계산 (트리 DP, 트리 지름, 최대 경로 합)
- 디렉토리 삭제도 post-order (자식 먼저 비우고 부모 삭제)

### 2.2 그래프 DFS — 인접 리스트

```
         0 ── 1
         │    │
         2 ── 3
              │
              4

adj = {0:[1,2], 1:[0,3], 2:[0,3], 3:[1,2,4], 4:[3]}

DFS(0) 호출 스택 추이:
    [0]
    [0, 1]                ← 0의 첫 이웃
    [0, 1, 3]
    [0, 1, 3, 2]          ← 3의 이웃 중 visited 안 한 2
    [0, 1, 3]             ← 2 끝, back
    [0, 1, 3, 4]
    [0, 1, 3]             ← 4 끝
    [0, 1]                ← 3 끝
    [0]                   ← 1 끝
    []                    ← 0 끝

방문 순서: 0 → 1 → 3 → 2 → 4
```

### 2.3 그리드 DFS — 4방향

```
grid = [
  [1, 1, 0, 0],
  [1, 0, 0, 1],
  [0, 0, 1, 1],
]

DFS(0,0):
  (0,0)→(0,1) [같은 행]
            →(1,1) X 0이라 skip
  (0,0)→(1,0)
            →(2,0) X
  → 첫 섬 완료 = {(0,0),(0,1),(1,0)}

DFS(1,3): {(1,3)} 단독
DFS(2,2): {(2,2),(2,3),(1,3)?} ← (1,3)은 이미 방문, 새 섬 = {(2,2),(2,3)}

방향 벡터:
  dr = {-1, 1, 0, 0}
  dc = { 0, 0,-1, 1}    ← 상하좌우

8방향 (대각 포함, 예: 지뢰찾기, 24문제):
  dr = {-1,-1,-1, 0, 0, 1, 1, 1}
  dc = {-1, 0, 1,-1, 1,-1, 0, 1}
```

### 2.4 재귀 호출 = JVM 콜 스택

```
[JVM Stack]              [Heap]

| dfs(node=4) |          ┌───────┐
| dfs(node=3) |          │  Node │  ← 객체는 Heap
| dfs(node=1) |          │   1   │
| dfs(node=0) |          ├───────┤
| main()      |          │  Node │
└─────────────┘          │   2   │
                         └───────┘

매 재귀 호출 = stack frame 1개:
  - return address
  - 지역 변수 (node, i, visited 참조 등)
  - 인자

Stack 영역 크기는 -Xss로 설정 (HotSpot 기본 512KB ~ 1MB).
프레임 1개 ~50 bytes → 깊이 ~10,000~20,000 가능.
이걸 넘으면 StackOverflowError.

→ N=10^6 그래프에서 chain 형태 입력이 들어오면 재귀 DFS는 폭발.
   대비책: iterative DFS (직접 Deque<Integer> stack 사용).
```

### 2.5 visited 마킹 — 두 위치의 차이

```
case A: 함수 진입 즉시 마킹 (들어갈 때)

dfs(u):
  if visited[u]: return         ← 가드
  visited[u] = true             ← 마킹
  for v in adj[u]:
    dfs(v)

→ 가장 표준. 어떤 경로로 들어오든 한 번만 처리.
→ 그리드 DFS, 연결 컴포넌트 카운팅에 사용.


case B: 자식 호출 직전에 가드 (in-line check)

dfs(u):
  visited[u] = true
  for v in adj[u]:
    if not visited[v]:          ← 가드
      dfs(v)

→ 동일 효과. 함수 호출 1회 줄임 (성능 미세 차이).


case C: 진입에 visited, 나갈 때 unvisited (backtracking)

dfs(path):
  if 조건: 결과 저장; return
  for choice in choices:
    visited[choice] = true
    path.add(choice)
    dfs(path)
    path.removeLast()           ← 되돌리기
    visited[choice] = false     ← 되돌리기

→ "모든 경로" 탐색. 같은 노드를 다른 경로로 다시 방문 가능해야 함.
→ DFS와 Backtracking의 분기점이 바로 이것.
```

### 2.6 DFS in/out time — discovery vs finish

```
       1
      / \
     2   5
    / \
   3   4

dfs(1)  in=1
  dfs(2)  in=2
    dfs(3)  in=3, out=4
    dfs(4)  in=5, out=6
  out=7
  dfs(5)  in=8, out=9
out=10

활용:
  - in time 순 = pre-order
  - out time 역순 = topological sort (사이클 없을 때)
  - in[u] ≤ in[v] ≤ out[v] ≤ out[u] ⇔ u는 v의 ancestor
```

### 2.7 DFS forest edge classification (방향 그래프)

```
DFS 도중 만나는 edge (u → v) 4종:

  Tree edge       : v가 아직 unvisited → 재귀 진입. DFS 트리의 간선.
  Back edge       : v가 visited & 현재 호출 스택에 있음 → 사이클!
  Forward edge    : v가 visited & 자손 (in[u]<in[v]<out[v]<out[u])
  Cross edge      : 위 셋 다 아님 (다른 서브트리)

운영 응용:
  - Back edge 존재 = 그래프에 사이클 = Spring bean DI 순환참조 검출
  - 사이클 없는 DAG → 위상정렬 가능 → 작업 의존성 schedule
```

### 2.8 iterative DFS — 스택 변환

```
재귀 DFS                 iterative DFS

dfs(u):                  Deque<Integer> stack = new ArrayDeque<>();
  visited[u] = true      stack.push(start);
  for v in adj[u]:       while (!stack.isEmpty()) {
    if !visited[v]:        int u = stack.pop();
      dfs(v)               if (visited[u]) continue;
                           visited[u] = true;
                           for (int v : adj[u]) {
                             if (!visited[v]) stack.push(v);
                           }
                         }

차이:
  - 방문 순서가 미세하게 다름 (adj를 역순으로 push해야 재귀와 동일)
  - StackOverflow 없음 (Heap을 씀)
  - return value 가지고 올라오기 어려움 → post-order는 추가 기교 필요
```

### 2.9 그리드 DFS 방문 마킹 순서

```
초기 그리드 (1=땅, 0=물):

  1 1 0
  1 0 0
  0 1 1

DFS(0,0) 시작, V로 방문 표시:

step 1:  V 1 0      ← (0,0) 마킹
         1 0 0
         0 1 1

step 2:  V V 0      ← (0,1) 방향 진행
         1 0 0
         0 1 1

step 3:  V V 0      ← (0,2)는 0, skip. back. (0,0)의 다른 방향: (1,0)
         V 0 0
         0 1 1

step 4:  V V 0      ← (1,0)의 이웃 (2,0)은 0, skip. back ... back.
         V 0 0
         0 1 1

첫 섬 완성: 3칸.
그 다음 외부 루프가 (2,1) 발견 → 새 DFS → 섬 2개.
```

---

## 3. 직관과 정의

### 3.1 한 줄 비유

미로에 들어가서 **갈 수 있는 데까지 한 방향으로 끝까지 간다**. 막다른 길이면 한 발 물러나 다른 방향 시도. 이 "한 발 물러남"이 재귀의 return.

### 3.2 정확한 정의

DFS는 그래프 G=(V,E)의 모든 정점을 다음 규칙으로 방문하는 알고리즘.

1. 시작 정점 s를 방문 표시.
2. s의 아직 방문 안 한 이웃 v를 골라 DFS(v)로 진입.
3. 더 이상 방문 안 한 이웃이 없으면 호출 반환.
4. 외부에서 모든 정점에 대해 1~3을 반복 (연결 컴포넌트가 여러 개일 수 있으므로).

### 3.3 왜 재귀가 자연스러운가

문제 자체가 재귀 구조다.

- "정점 u에서 도달 가능한 정점 집합" = {u} ∪ ⋃ {정점 v에서 도달 가능한 집합 | (u,v) ∈ E}
- 트리의 깊이 = 1 + max(왼쪽 자식의 깊이, 오른쪽 자식의 깊이)
- 섬의 크기 = 1 + 4방향 이웃의 섬의 크기 (visited 가드)

수학 정의가 그대로 재귀 코드로 떨어진다.

### 3.4 스택 변환과의 관계

재귀 호출 = JVM이 자동 관리하는 stack frame. 이걸 명시적 `Deque`로 옮기면 iterative DFS. 본질적으로 동일하지만:

- 재귀 — 코드 짧음, return value 자연스럽게 누적, 깊이 제한
- iterative — 코드 길고 복잡, deep input 안전, post-order 구현 까다로움

### 3.5 visited[] 위치 결정 트리

```
Q1. 같은 노드를 다른 경로로 다시 봐야 하나?
    │
    NO ──▶ 진입 즉시 마킹 (case A/B). DFS의 기본 형태.
    │       예: 섬 개수, 트리 순회, 연결 컴포넌트
    │
    YES ─▶ 진입 마킹 + return 직전 unmark (case C). Backtracking.
            예: 모든 경로 출력, 순열, N-Queen, 미로 모든 답

Q2. 마킹 안 하면?
    무한 루프 (그래프에 사이클 있을 때) → StackOverflowError.
```

---

## 4. Java 템플릿 — 4가지 변형

### 4.1 그리드 DFS

```java
class GridDFS {
    private int[][] grid;
    private boolean[][] visited;
    private int R, C;
    private static final int[] DR = {-1, 1, 0, 0};
    private static final int[] DC = {0, 0, -1, 1};

    public int solve(int[][] g) {
        this.grid = g;
        this.R = g.length;
        this.C = g[0].length;
        this.visited = new boolean[R][C];
        int count = 0;
        for (int r = 0; r < R; r++) {
            for (int c = 0; c < C; c++) {
                if (grid[r][c] == 1 && !visited[r][c]) {
                    dfs(r, c);
                    count++;
                }
            }
        }
        return count;
    }

    private void dfs(int r, int c) {
        // 1) 경계
        if (r < 0 || r >= R || c < 0 || c >= C) return;
        // 2) 방문 가드
        if (visited[r][c] || grid[r][c] != 1) return;
        // 3) 방문 표시
        visited[r][c] = true;
        // 4) 4방향 재귀
        for (int d = 0; d < 4; d++) {
            dfs(r + DR[d], c + DC[d]);
        }
    }
}
```

### 4.2 그래프 DFS — 인접 리스트

```java
class GraphDFS {
    private List<List<Integer>> adj;
    private boolean[] visited;

    public int countComponents(int n, int[][] edges) {
        adj = new ArrayList<>();
        for (int i = 0; i < n; i++) adj.add(new ArrayList<>());
        for (int[] e : edges) {
            adj.get(e[0]).add(e[1]);
            adj.get(e[1]).add(e[0]); // 무방향
        }
        visited = new boolean[n];
        int components = 0;
        for (int i = 0; i < n; i++) {
            if (!visited[i]) {
                dfs(i);
                components++;
            }
        }
        return components;
    }

    private void dfs(int u) {
        visited[u] = true;
        for (int v : adj.get(u)) {
            if (!visited[v]) dfs(v);
        }
    }
}
```

### 4.3 트리 DFS — post-order로 자식 결과 집계

```java
class TreeDFS {
    // Definition for a binary tree node.
    static class TreeNode {
        int val;
        TreeNode left, right;
        TreeNode(int v) { val = v; }
    }

    public int maxDepth(TreeNode root) {
        if (root == null) return 0;
        int left = maxDepth(root.left);    // 왼쪽 자식 결과
        int right = maxDepth(root.right);  // 오른쪽 자식 결과
        return 1 + Math.max(left, right);  // post-order: 자식 결과로 자기 계산
    }
}
```

### 4.4 Iterative DFS — Deque<Integer> 스택

```java
class IterativeDFS {
    public void dfs(int start, List<List<Integer>> adj) {
        int n = adj.size();
        boolean[] visited = new boolean[n];
        Deque<Integer> stack = new ArrayDeque<>();
        stack.push(start);
        while (!stack.isEmpty()) {
            int u = stack.pop();
            if (visited[u]) continue;
            visited[u] = true;
            // 처리: System.out.println(u);
            // 재귀와 동일한 순서를 원하면 역순 push
            List<Integer> nbrs = adj.get(u);
            for (int i = nbrs.size() - 1; i >= 0; i--) {
                int v = nbrs.get(i);
                if (!visited[v]) stack.push(v);
            }
        }
    }
}
```

언제 iterative로? `N ≥ 10^5`이고 chain 입력 가능성, 또는 `-Xss` 늘리기 어려운 환경 (서버리스).

---

## 5. Kotlin 템플릿 — 4가지 변형

### 5.1 그리드 DFS

```kotlin
class GridDFS {
    private lateinit var grid: Array<IntArray>
    private lateinit var visited: Array<BooleanArray>
    private var R = 0
    private var C = 0
    private val dr = intArrayOf(-1, 1, 0, 0)
    private val dc = intArrayOf(0, 0, -1, 1)

    fun solve(g: Array<IntArray>): Int {
        grid = g
        R = g.size
        C = g[0].size
        visited = Array(R) { BooleanArray(C) }
        var count = 0
        for (r in 0 until R) {
            for (c in 0 until C) {
                if (grid[r][c] == 1 && !visited[r][c]) {
                    dfs(r, c)
                    count++
                }
            }
        }
        return count
    }

    private fun dfs(r: Int, c: Int) {
        if (r !in 0 until R || c !in 0 until C) return
        if (visited[r][c] || grid[r][c] != 1) return
        visited[r][c] = true
        for (d in 0 until 4) dfs(r + dr[d], c + dc[d])
    }
}
```

### 5.2 그래프 DFS

```kotlin
class GraphDFS {
    fun countComponents(n: Int, edges: Array<IntArray>): Int {
        val adj = Array(n) { mutableListOf<Int>() }
        for ((u, v) in edges) {
            adj[u].add(v)
            adj[v].add(u)
        }
        val visited = BooleanArray(n)
        var components = 0
        fun dfs(u: Int) {
            visited[u] = true
            for (v in adj[u]) if (!visited[v]) dfs(v)
        }
        for (i in 0 until n) {
            if (!visited[i]) {
                dfs(i)
                components++
            }
        }
        return components
    }
}
```

`fun dfs` 안에 fun을 정의하는 local function — Kotlin 관용이며 외부 상태(`visited`, `adj`)에 자연스럽게 접근.

### 5.3 트리 DFS

```kotlin
class TreeDFS {
    class TreeNode(var `val`: Int, var left: TreeNode? = null, var right: TreeNode? = null)

    fun maxDepth(root: TreeNode?): Int {
        if (root == null) return 0
        return 1 + maxOf(maxDepth(root.left), maxDepth(root.right))
    }
}
```

### 5.4 Iterative DFS

```kotlin
class IterativeDFS {
    fun dfs(start: Int, adj: List<List<Int>>) {
        val visited = BooleanArray(adj.size)
        val stack = ArrayDeque<Int>()
        stack.addLast(start)
        while (stack.isNotEmpty()) {
            val u = stack.removeLast()
            if (visited[u]) continue
            visited[u] = true
            // 처리
            for (i in adj[u].indices.reversed()) {
                val v = adj[u][i]
                if (!visited[v]) stack.addLast(v)
            }
        }
    }
}
```

Kotlin의 `ArrayDeque`는 deque인데 `addLast/removeLast`를 쓰면 stack처럼 동작 (LIFO).

---

## 6. 시간/공간 복잡도

### 6.1 그래프 DFS

- 시간: **O(V + E)** — 각 정점 1회, 각 간선 1회 검사 (인접 리스트 가정).
- 공간: **O(V)** — visited 배열 + 재귀 스택 깊이 최대 V (chain일 때).
- 인접 행렬이면 시간 **O(V²)** — 각 정점에서 모든 정점 검사.

### 6.2 그리드 DFS

- 시간: **O(R × C)** — 각 셀 1회 방문.
- 공간: **O(R × C)** — visited + 최악의 경우 스택 깊이 R*C (지그재그 한 줄 모양).

### 6.3 트리 DFS

- 시간: **O(N)** — 노드 1회.
- 공간: **O(H)** — H는 트리 높이. 균형 트리면 O(logN), skewed면 O(N).

### 6.4 BFS와의 메모리 비교

같은 그래프에서:

- DFS 스택 깊이: 그래프 깊이 만큼 (최악 V).
- BFS 큐 크기: 같은 레벨의 최대 너비 (그리드에서는 min(R,C), 트리에서는 leaf 수 ~ N/2).

→ "메모리는 DFS가 항상 적다"는 거짓. **모양에 따라 다름**. 깊고 좁으면 BFS 유리, 넓고 얕으면 DFS 유리.

---

## 7. 대표 문제 8개

### 7.1 LeetCode 200 — Number of Islands

> `'1'`(land)과 `'0'`(water)로 된 m×n 그리드에서 섬의 개수를 반환.

**접근**: 모든 셀을 순회하며 미방문 land를 만나면 DFS로 같은 섬 전체를 방문 마킹, 카운터 +1.

**Java**:

```java
class Solution {
    private char[][] grid;
    private int R, C;
    public int numIslands(char[][] grid) {
        this.grid = grid;
        this.R = grid.length;
        this.C = grid[0].length;
        int count = 0;
        for (int r = 0; r < R; r++) {
            for (int c = 0; c < C; c++) {
                if (grid[r][c] == '1') {
                    dfs(r, c);
                    count++;
                }
            }
        }
        return count;
    }
    private void dfs(int r, int c) {
        if (r < 0 || r >= R || c < 0 || c >= C) return;
        if (grid[r][c] != '1') return;
        grid[r][c] = '#';  // visited 별도 배열 대신 원본 변경
        dfs(r-1, c); dfs(r+1, c); dfs(r, c-1); dfs(r, c+1);
    }
}
```

**Kotlin**:

```kotlin
class Solution {
    fun numIslands(grid: Array<CharArray>): Int {
        val R = grid.size
        val C = grid[0].size
        fun dfs(r: Int, c: Int) {
            if (r !in 0 until R || c !in 0 until C) return
            if (grid[r][c] != '1') return
            grid[r][c] = '#'
            dfs(r-1, c); dfs(r+1, c); dfs(r, c-1); dfs(r, c+1)
        }
        var count = 0
        for (r in 0 until R) for (c in 0 until C) {
            if (grid[r][c] == '1') { dfs(r, c); count++ }
        }
        return count
    }
}
```

**복잡도**: O(R*C) 시간, O(R*C) 공간 (재귀).

**함정**:
- 원본 grid 변경 vs visited 배열 — 면접관이 "원본 보존" 요구하면 visited 배열 필요.
- `char vs int` — LeetCode 200은 char로 줌. 비교 시 작은 따옴표.
- 4방향만 검사 (대각 X). 문제 문구를 정확히 읽을 것.

### 7.2 LeetCode 695 — Max Area of Island

> 섬의 최대 면적.

**접근**: DFS가 면적(=방문한 칸 수)을 return.

**Java**:

```java
class Solution {
    private int[][] grid;
    private int R, C;
    public int maxAreaOfIsland(int[][] grid) {
        this.grid = grid;
        this.R = grid.length;
        this.C = grid[0].length;
        int max = 0;
        for (int r = 0; r < R; r++) {
            for (int c = 0; c < C; c++) {
                if (grid[r][c] == 1) {
                    max = Math.max(max, dfs(r, c));
                }
            }
        }
        return max;
    }
    private int dfs(int r, int c) {
        if (r < 0 || r >= R || c < 0 || c >= C) return 0;
        if (grid[r][c] != 1) return 0;
        grid[r][c] = 0;
        return 1 + dfs(r-1,c) + dfs(r+1,c) + dfs(r,c-1) + dfs(r,c+1);
    }
}
```

**Kotlin**:

```kotlin
class Solution {
    fun maxAreaOfIsland(grid: Array<IntArray>): Int {
        val R = grid.size; val C = grid[0].size
        fun dfs(r: Int, c: Int): Int {
            if (r !in 0 until R || c !in 0 until C) return 0
            if (grid[r][c] != 1) return 0
            grid[r][c] = 0
            return 1 + dfs(r-1,c) + dfs(r+1,c) + dfs(r,c-1) + dfs(r,c+1)
        }
        var max = 0
        for (r in 0 until R) for (c in 0 until C) {
            if (grid[r][c] == 1) max = maxOf(max, dfs(r, c))
        }
        return max
    }
}
```

**복잡도**: O(R*C).

**함정**:
- DFS가 면적을 return하도록 시그니처를 `int`로. void로 짜면 외부 변수 누적 필요해서 코드 더 김.
- 빈 그리드 (모두 0) → 0 반환. 문제 없음 (max 초기값 0).

### 7.3 LeetCode 130 — Surrounded Regions

> `O`로 둘러싸인 영역을 `X`로 변경. **경계와 닿은 `O`는 보존**.

**접근**: 역발상 — 경계에서 시작해서 DFS로 도달 가능한 `O`를 임시 마커 `#`으로 변경. 끝나면 `O→X`, `#→O`.

**Java**:

```java
class Solution {
    private char[][] b;
    private int R, C;
    public void solve(char[][] board) {
        this.b = board;
        this.R = board.length;
        this.C = board[0].length;
        // 경계 O에서 DFS
        for (int r = 0; r < R; r++) {
            dfs(r, 0); dfs(r, C-1);
        }
        for (int c = 0; c < C; c++) {
            dfs(0, c); dfs(R-1, c);
        }
        // 마무리
        for (int r = 0; r < R; r++) {
            for (int c = 0; c < C; c++) {
                if (b[r][c] == 'O') b[r][c] = 'X';
                else if (b[r][c] == '#') b[r][c] = 'O';
            }
        }
    }
    private void dfs(int r, int c) {
        if (r < 0 || r >= R || c < 0 || c >= C) return;
        if (b[r][c] != 'O') return;
        b[r][c] = '#';
        dfs(r-1,c); dfs(r+1,c); dfs(r,c-1); dfs(r,c+1);
    }
}
```

**Kotlin**:

```kotlin
class Solution {
    fun solve(board: Array<CharArray>) {
        val R = board.size; val C = board[0].size
        fun dfs(r: Int, c: Int) {
            if (r !in 0 until R || c !in 0 until C) return
            if (board[r][c] != 'O') return
            board[r][c] = '#'
            dfs(r-1,c); dfs(r+1,c); dfs(r,c-1); dfs(r,c+1)
        }
        for (r in 0 until R) { dfs(r, 0); dfs(r, C-1) }
        for (c in 0 until C) { dfs(0, c); dfs(R-1, c) }
        for (r in 0 until R) for (c in 0 until C) {
            when (board[r][c]) {
                'O' -> board[r][c] = 'X'
                '#' -> board[r][c] = 'O'
            }
        }
    }
}
```

**복잡도**: O(R*C).

**함정**:
- "경계 O는 보존"을 처음부터 따라가면 복잡 — **역발상**. 보존할 것을 먼저 표시.
- 임시 마커는 입력에 없는 문자 (여기 `#`). 그냥 `'O'` 그대로 두면 두 번째 패스에서 구분 불가.

### 7.4 LeetCode 417 — Pacific Atlantic Water Flow

> 격자의 높이 맵. 좌상단/상단 경계는 Pacific, 우/하단은 Atlantic. 물은 같거나 낮은 곳으로 흐름. **두 바다 모두에 도달 가능한 셀**을 반환.

**접근**: 역시 역발상 — 바다에서 거꾸로 올라가기. 각 셀이 Pacific에서 도달 가능한지(높이가 오르막일 때 진행), Atlantic에서 도달 가능한지 두 boolean 그리드. 둘 다 true인 셀만 결과.

**Java**:

```java
class Solution {
    private int[][] h;
    private int R, C;
    public List<List<Integer>> pacificAtlantic(int[][] heights) {
        this.h = heights;
        this.R = heights.length;
        this.C = heights[0].length;
        boolean[][] pac = new boolean[R][C];
        boolean[][] atl = new boolean[R][C];
        // Pacific: top row + left col
        for (int c = 0; c < C; c++) dfs(0, c, pac, Integer.MIN_VALUE);
        for (int r = 0; r < R; r++) dfs(r, 0, pac, Integer.MIN_VALUE);
        // Atlantic: bottom row + right col
        for (int c = 0; c < C; c++) dfs(R-1, c, atl, Integer.MIN_VALUE);
        for (int r = 0; r < R; r++) dfs(r, C-1, atl, Integer.MIN_VALUE);
        List<List<Integer>> ans = new ArrayList<>();
        for (int r = 0; r < R; r++) {
            for (int c = 0; c < C; c++) {
                if (pac[r][c] && atl[r][c]) ans.add(List.of(r, c));
            }
        }
        return ans;
    }
    private void dfs(int r, int c, boolean[][] seen, int prev) {
        if (r < 0 || r >= R || c < 0 || c >= C) return;
        if (seen[r][c]) return;
        if (h[r][c] < prev) return;  // 거꾸로 = 오르막만 진행
        seen[r][c] = true;
        dfs(r-1, c, seen, h[r][c]);
        dfs(r+1, c, seen, h[r][c]);
        dfs(r, c-1, seen, h[r][c]);
        dfs(r, c+1, seen, h[r][c]);
    }
}
```

**Kotlin**:

```kotlin
class Solution {
    fun pacificAtlantic(heights: Array<IntArray>): List<List<Int>> {
        val R = heights.size; val C = heights[0].size
        val pac = Array(R) { BooleanArray(C) }
        val atl = Array(R) { BooleanArray(C) }
        fun dfs(r: Int, c: Int, seen: Array<BooleanArray>, prev: Int) {
            if (r !in 0 until R || c !in 0 until C) return
            if (seen[r][c]) return
            if (heights[r][c] < prev) return
            seen[r][c] = true
            val cur = heights[r][c]
            dfs(r-1, c, seen, cur); dfs(r+1, c, seen, cur)
            dfs(r, c-1, seen, cur); dfs(r, c+1, seen, cur)
        }
        for (c in 0 until C) dfs(0, c, pac, Int.MIN_VALUE)
        for (r in 0 until R) dfs(r, 0, pac, Int.MIN_VALUE)
        for (c in 0 until C) dfs(R-1, c, atl, Int.MIN_VALUE)
        for (r in 0 until R) dfs(r, C-1, atl, Int.MIN_VALUE)
        val ans = mutableListOf<List<Int>>()
        for (r in 0 until R) for (c in 0 until C) {
            if (pac[r][c] && atl[r][c]) ans.add(listOf(r, c))
        }
        return ans
    }
}
```

**복잡도**: O(R*C) — 각 셀이 두 그리드에서 최대 1번씩 방문.

**함정**:
- 정방향 (셀에서 바다로) 시뮬레이션은 매 셀마다 DFS → O((R*C)²). TLE.
- 역방향이면 시작점이 R+C개 정도 → O(R*C).
- 비교는 `>=` (같은 높이도 흐름 가능). 거꾸로 올라갈 때는 `h[next] >= h[prev]`.

### 7.5 LeetCode 104 — Maximum Depth of Binary Tree

> 이진 트리의 최대 깊이.

**Java**:

```java
class Solution {
    public int maxDepth(TreeNode root) {
        if (root == null) return 0;
        return 1 + Math.max(maxDepth(root.left), maxDepth(root.right));
    }
}
```

**Kotlin**:

```kotlin
class Solution {
    fun maxDepth(root: TreeNode?): Int {
        if (root == null) return 0
        return 1 + maxOf(maxDepth(root.left), maxDepth(root.right))
    }
}
```

**복잡도**: O(N) 시간, O(H) 스택.

**함정**: 빈 트리(`null`) → 0. 단일 노드 → 1. 한 줄 풀이지만 면접에서는 **iterative BFS 풀이도 함께 물음** — 매 레벨 단위로 깊이 카운트.

### 7.6 LeetCode 543 — Diameter of Binary Tree

> 트리의 어느 두 노드 사이 가장 긴 경로의 **edge 수**.

**접근**: 각 노드에서 `depth(left) + depth(right)`가 그 노드를 지나는 가장 긴 경로. 전역 max 갱신하면서 post-order로 depth return.

**Java**:

```java
class Solution {
    private int diameter = 0;
    public int diameterOfBinaryTree(TreeNode root) {
        depth(root);
        return diameter;
    }
    private int depth(TreeNode node) {
        if (node == null) return 0;
        int l = depth(node.left);
        int r = depth(node.right);
        diameter = Math.max(diameter, l + r);  // 이 노드를 꼭대기로 한 경로
        return 1 + Math.max(l, r);            // 부모에게 반환할 깊이
    }
}
```

**Kotlin**:

```kotlin
class Solution {
    private var diameter = 0
    fun diameterOfBinaryTree(root: TreeNode?): Int {
        depth(root)
        return diameter
    }
    private fun depth(node: TreeNode?): Int {
        if (node == null) return 0
        val l = depth(node.left)
        val r = depth(node.right)
        diameter = maxOf(diameter, l + r)
        return 1 + maxOf(l, r)
    }
}
```

**복잡도**: O(N).

**함정**:
- "edge 수" vs "node 수" — LeetCode 543은 edge. 그래서 `l+r`이고 `l+r+1`이 아님.
- 한 함수가 두 가지 일을 함: (1) 전역 답 갱신, (2) 호출자에게 깊이 반환. **트리 DP의 표준 패턴**.

### 7.7 LeetCode 124 — Binary Tree Maximum Path Sum

> 임의의 두 노드를 잇는 경로의 노드 값 합의 최댓값. (값은 음수 가능.)

**접근**: 543의 일반화. 각 노드에서 "이 노드를 꼭대기로 하는 경로 합" = `node.val + max(0, leftGain) + max(0, rightGain)`. 호출자에게 반환은 "한 쪽 가지만" = `node.val + max(0, max(leftGain, rightGain))`.

**Java**:

```java
class Solution {
    private int best = Integer.MIN_VALUE;
    public int maxPathSum(TreeNode root) {
        gain(root);
        return best;
    }
    private int gain(TreeNode node) {
        if (node == null) return 0;
        int l = Math.max(0, gain(node.left));   // 음수면 끊기
        int r = Math.max(0, gain(node.right));
        best = Math.max(best, node.val + l + r); // 이 노드 꼭대기로 한 경로
        return node.val + Math.max(l, r);        // 부모에 반환은 한 쪽만
    }
}
```

**Kotlin**:

```kotlin
class Solution {
    private var best = Int.MIN_VALUE
    fun maxPathSum(root: TreeNode?): Int {
        gain(root)
        return best
    }
    private fun gain(node: TreeNode?): Int {
        if (node == null) return 0
        val l = maxOf(0, gain(node.left))
        val r = maxOf(0, gain(node.right))
        best = maxOf(best, node.`val` + l + r)
        return node.`val` + maxOf(l, r)
    }
}
```

**복잡도**: O(N).

**함정**:
- `best`의 초기값은 `Integer.MIN_VALUE`. **모든 값이 음수**일 수 있음 (예: `[-3]`).
- 부모에게 반환할 때는 한 쪽 가지만. 양쪽 다 합치면 경로가 분기되어 정의에 어긋남.
- `max(0, ...)`로 음수 가지를 끊는 것이 핵심.

### 7.8 Programmers — 타겟 넘버 / 네트워크

> 타겟 넘버: 음이 아닌 정수 배열 numbers + target. 각 수에 +/- 부여해서 합이 target이 되는 경우의 수.
> 네트워크: n×n 인접 행렬. 연결 컴포넌트 개수.

**타겟 넘버 — DFS + backtracking 맛**:

**Java**:

```java
class Solution {
    private int count = 0;
    private int[] numbers;
    private int target;
    public int solution(int[] numbers, int target) {
        this.numbers = numbers;
        this.target = target;
        dfs(0, 0);
        return count;
    }
    private void dfs(int idx, int sum) {
        if (idx == numbers.length) {
            if (sum == target) count++;
            return;
        }
        dfs(idx + 1, sum + numbers[idx]);  // +
        dfs(idx + 1, sum - numbers[idx]);  // -
    }
}
```

**Kotlin**:

```kotlin
class Solution {
    private var count = 0
    fun solution(numbers: IntArray, target: Int): Int {
        fun dfs(idx: Int, sum: Int) {
            if (idx == numbers.size) {
                if (sum == target) count++
                return
            }
            dfs(idx + 1, sum + numbers[idx])
            dfs(idx + 1, sum - numbers[idx])
        }
        dfs(0, 0)
        return count
    }
}
```

**복잡도**: O(2^N) — N은 numbers 길이 ≤ 20.

**함정**:
- `numbers`에 0이 들어올 수 있음 — `+0` `-0` 둘 다 별개로 카운트.
- 이 문제는 사실 DP로 O(N*S)에 가능. 면접에서 "더 빠르게?" 물으면 DP 언급할 것.

**네트워크 — 그래프 DFS**:

**Java**:

```java
class Solution {
    public int solution(int n, int[][] computers) {
        boolean[] visited = new boolean[n];
        int count = 0;
        for (int i = 0; i < n; i++) {
            if (!visited[i]) {
                dfs(i, computers, visited);
                count++;
            }
        }
        return count;
    }
    private void dfs(int u, int[][] computers, boolean[] visited) {
        visited[u] = true;
        for (int v = 0; v < computers.length; v++) {
            if (computers[u][v] == 1 && !visited[v]) dfs(v, computers, visited);
        }
    }
}
```

**Kotlin**:

```kotlin
class Solution {
    fun solution(n: Int, computers: Array<IntArray>): Int {
        val visited = BooleanArray(n)
        fun dfs(u: Int) {
            visited[u] = true
            for (v in 0 until n) {
                if (computers[u][v] == 1 && !visited[v]) dfs(v)
            }
        }
        var count = 0
        for (i in 0 until n) {
            if (!visited[i]) { dfs(i); count++ }
        }
        return count
    }
}
```

**복잡도**: O(N²) — 인접 행렬이므로 각 정점에서 N개 확인.

**함정**:
- 인접 **행렬** 입력 — 인접 리스트 변환 없이 바로 순회.
- `computers[u][u] == 1` (자기 자신) — 들어와도 visited 가드로 무한 루프 안 됨.

---

## 8. 함정·엣지케이스

### 8.1 StackOverflowError — JVM 기본 스택 ~10K 깊이

```java
// 깊이 10^6의 그래프 (chain): 0 → 1 → 2 → ... → 999999
// 재귀 DFS → StackOverflowError
```

**원인**: HotSpot의 `-Xss` 기본값은 OS/JVM 버전에 따라 256KB ~ 1MB. 프레임당 ~50~100 bytes → 안전 깊이 약 5,000 ~ 20,000.

**대비책**:
1. **Iterative DFS** — 명시적 `Deque` 사용. Heap에 들어가므로 깊이 제한 = 사실상 N.
2. **`-Xss` 늘리기** — `java -Xss64m Main`. 로컬 테스트엔 OK, 클라우드 배포에는 위험 (메모리 N배 증가).
3. **별도 스레드에서 실행** — Thread 생성 시 stack 크기 지정: `new Thread(null, runnable, "name", 64 * 1024 * 1024)`. 알고리즘 대회/저지 환경에서 자주 쓰이는 트릭.

```java
// 깊은 DFS가 필요할 때 표준 트릭 — 큰 stack을 가진 별도 스레드에서 실행
public class Main {
    public static void main(String[] args) {
        new Thread(null, Main::solve, "main", 1 << 26).start(); // 64MB stack
    }
    static void solve() {
        // 여기서 DFS
    }
}
```

### 8.2 visited 마킹 위치 — 진입 직후 vs 자식 호출 전

```java
// BAD: 자식 마다 마킹
void dfs(int u) {
    for (int v : adj.get(u)) {
        visited[v] = true;  // ← 잘못
        dfs(v);
    }
}
// → 시작점 u가 마킹 안 됨. 다른 노드가 u로 돌아오면 다시 들어감.

// GOOD: 진입 즉시
void dfs(int u) {
    visited[u] = true;
    for (int v : adj.get(u)) {
        if (!visited[v]) dfs(v);
    }
}
```

### 8.3 무방향 그래프에서 부모 노드 재방문

```
   0 ── 1
adj[0] = [1], adj[1] = [0]

dfs(0):
  visited[0] = true
  for v in adj[0]:  // [1]
    if !visited[1]: dfs(1)
      visited[1] = true
      for v in adj[1]:  // [0]
        if !visited[0]:  // false → 들어가지 않음 ✓
```

→ `visited` 가드만 잘 있으면 부모 재방문은 자동 방지. **하지만** 사이클 검출 같은 특수 목적에서는 parent 인자를 받아서 더 명시적으로 거를 수 있음:

```java
boolean hasCycle(int u, int parent) {
    visited[u] = true;
    for (int v : adj.get(u)) {
        if (!visited[v]) {
            if (hasCycle(v, u)) return true;
        } else if (v != parent) {
            return true;  // 부모가 아닌데 visited == back edge == cycle
        }
    }
    return false;
}
```

### 8.4 그리드 dr/dc 배열 순서

순서는 결과에 영향 없지만(어차피 모두 방문) **다익스트라/BFS 최단경로 출력**에선 같은 거리일 때 출력 순서가 달라짐. 문제가 "lexicographically smallest path" 같은 걸 요구하면 dr/dc 순서 의식.

### 8.5 빈 입력 / 단일 노드 / null

| 케이스 | 대응 |
|---|---|
| `grid.length == 0` | for 루프 안 돈다. count = 0 반환. |
| `root == null` | base case로 0 또는 null 반환. |
| `n == 1, edges == []` | 연결 컴포넌트 1개. |
| 모든 셀이 물 | count = 0. |
| 모든 셀이 땅 | count = 1. |

### 8.6 grid 변경 vs visited 배열

- **grid 변경**: 메모리 절약 (O(1) 추가), 빠름. 단점: 원본 손상. **호출자가 보존을 요구**하면 안 됨.
- **visited 배열**: 원본 보존. O(R*C) 추가. 면접에서는 보통 visited 권장 — 깔끔.

### 8.7 sum overflow

LeetCode 124 같은 트리 경로 합 — 값이 음수~양수 섞이지만 N ≤ 3*10^4, val ∈ [-1000, 1000] → 최악 3*10^7로 `int` 안전. 하지만 더 큰 범위 (예: N ≥ 10^5, val ≥ 10^5)면 `long`으로 받아야 overflow를 피한다.

### 8.8 재귀 cost vs JIT inlining

JIT 컴파일러는 재귀를 inline하기 어려움. 코드 핫스팟에서 깊은 재귀가 보이면 iterative + 명시 스택이 마이크로 벤치마크상 1.5~2배 빠른 경우 많음. 코딩 테스트에서는 의미 없지만 production에서는 차이가 보임.

---

## 9. 꼬리질문 트리

```
Q1. "DFS와 BFS 중 왜 DFS?"
   A. (1) 깊이 우선이 자연스러운 문제 (모든 경로/연결 컴포넌트/트리 깊이)
      (2) 메모리: 트리가 wide & shallow면 BFS 큐가 leaf 수만큼 커짐 → DFS의 스택이 더 작음
      (3) 코드 간결성 (재귀 한 줄)
      반대로 최단 거리(가중치 없음)면 무조건 BFS.

Q2. "재귀를 iterative로 바꾸려면?"
   A. Deque<T> stack 만들어서:
      - 재귀 진입 = push
      - return = pop
      - 인자 묶음을 Pair나 int[]로 push
      - post-order 결과 누적이 필요하면 "방문 단계" enum 사용 (Tarjan style)

Q3. "큰 그래프에서 StackOverflow 방지하려면?"
   A. (1) iterative + 명시 스택
      (2) -Xss 늘리기 (로컬만)
      (3) 별도 스레드에 stack 크기 지정해서 그 안에서 DFS 실행
      (4) tail recursion? — Java/Kotlin은 TCO 없음. Kotlin은 tailrec 키워드 있지만 DFS는 보통 tailrec 안 됨 (이중 재귀).

Q4. "DFS로 위상정렬?"
   A. Post-order 종료 순서의 역순 = 위상 정렬.
      void dfs(u): visited[u]=true; for v: if !visited dfs(v); stack.push(u);
      모든 노드 DFS 후 stack을 pop하면 위상 순서.
      단, 사이클 있으면 위상 정렬 불가 → back edge 검출 필요 (별도 onStack 배열).

Q5. "DFS forest의 edge classification?"
   A. 4종류 (방향 그래프 기준):
      - Tree edge: DFS 트리의 간선
      - Back edge: 자기 ancestor로 (cycle 존재)
      - Forward edge: 자기 자손으로 (이미 visited)
      - Cross edge: 다른 subtree
      Discovery time(in)/Finish time(out) 가지고 분류:
        in[u] < in[v] < out[v] < out[u]  → 자손 (tree or forward)
        in[v] < in[u] < out[u] < out[v]  → ancestor (back)
        in[v] < out[v] < in[u]           → cross

Q6. "사이클 검출 — 무방향 vs 방향?"
   A. 무방향: parent 인자 들고 다니며 "parent 아닌 visited 이웃" 보면 cycle.
      방향: onStack 배열 (현재 DFS path에 있는 노드만 표시).
            visited만 보면 cross edge도 cycle로 오인.

Q7. "DFS의 공간 복잡도가 BFS보다 항상 작은가?"
   A. 아니다. 그래프 모양에 따라.
      - 깊고 좁은 트리/그래프: DFS 스택 깊이 = 길이, BFS 큐 = 너비 → BFS 유리
      - 넓고 얕은: DFS 유리
      그리드는 일반적으로 BFS 큐가 작음 (한 레벨이 둘레 길이).

Q8. "재귀 함수의 메모리 부담을 정확히 어떻게 측정?"
   A. JFR (Java Flight Recorder) → Thread Stack Profile
      또는 Thread.getAllStackTraces()로 스냅샷.
      OOM 시 java.lang.StackOverflowError는 Heap 아닌 Stack 영역 고갈.
      -Xss로 모니터링.
```

---

## 10. 다른 패턴과의 연결

### 10.1 BFS와의 사용 시점 차이

| 신호 | DFS | BFS |
|---|---|---|
| 최단 거리 (unweighted) | X | O |
| 모든 경로 탐색 | O | X (복잡) |
| 연결 컴포넌트 카운트 | O | O (둘 다 OK) |
| 트리 레벨 순회 | X | O |
| 트리 깊이/지름 | O (post-order) | X |
| 깊고 좁은 그래프 | O (메모리 작음) | X |
| 넓고 얕은 그래프 | X (스택 깊음 — 사실은 작음) | O |

### 10.2 Backtracking = DFS + 되돌리기

```
DFS:
  진입 시 visited 마킹, 끝까지 가고 반환. 마킹 해제 X.
  목적: 한 번이라도 도달한 노드를 다시 안 볼 것.

Backtracking:
  진입 시 path 추가 + visited 마킹.
  반환 직전에 path pop + visited 해제.
  목적: 같은 노드를 다른 경로로 다시 갈 수 있어야 함 (모든 경로 열거).

코드 차이는 단 두 줄:
  path.add(...)         ← 진입
    dfs(next)
  path.removeLast()     ← 반환 직전 (← 이게 핵심)
  visited[...] = false  ← 반환 직전
```

→ 10장 Backtracking은 DFS의 직접 후속이므로 DFS를 완전히 익혀야 함.

### 10.3 Tree 순회의 일반화

이진 트리의 pre/in/post-order는 **그래프 DFS의 특수 케이스** (자식이 2개로 제한, 사이클 없음, visited 불필요).

- pre-order ≡ "방문 처리 → 자식 재귀"
- post-order ≡ "자식 재귀 → 방문 처리"
- in-order는 이진 트리에만 의미 있음 (left → root → right)

일반 트리/그래프에서는 in-order 개념이 없음.

### 10.4 Graph 알고리즘의 빌딩 블록

- **위상 정렬** = DFS post-order 역순 (또는 Kahn의 BFS).
- **Tarjan SCC** = DFS + lowlink.
- **Bridge / Articulation point** = DFS + lowlink.
- **Eulerian path** = Hierholzer = iterative DFS 특수.

→ 11장 Graph의 핵심 알고리즘 다수가 DFS 기반. DFS가 안 되면 11장 못 함.

### 10.5 DP와의 연결 — Memoization

```
재귀 DFS + 결과 캐시 = top-down DP

int dfs(int state) {
    if (memo[state] != -1) return memo[state];
    int result = ...; // 재귀 호출
    return memo[state] = result;
}
```

LeetCode 329 Longest Increasing Path in a Matrix가 대표 예. 그리드 DFS + memo.

---

## 11. 시니어 운영 연결

### 11.1 디렉토리 트리 walk

```java
// java.nio.file.Files.walk — 내부적으로 DFS
try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile)
         .forEach(p -> process(p));
}
```

- `Files.walk` 기본은 lazy DFS. depth 제한이 없으면 deep symlink loop가 무한 루프 — `FOLLOW_LINKS` 옵션 + `maxDepth` 인자로 가드.
- `Files.walkFileTree`는 명시적 visitor 패턴. 디렉토리 진입/이탈 hook을 줘서 post-order 작업 (예: rm -rf의 자식 삭제 후 부모 삭제) 가능.
- production에서 `find /` 같은 walk가 너무 깊어서 OOM이 발생한 케이스 다수. 항상 maxDepth, prune 조건 필수.

### 11.2 Spring DI 순환참조 검출

```
@Service
class A { @Autowired B b; }
@Service
class B { @Autowired A a; }   // 순환

→ Spring boot startup 시 BeanCurrentlyInCreationException.
```

내부적으로 Spring은 bean 의존성 그래프에서 DFS를 돌며 currently-creating 집합(=DFS 호출 스택)에 같은 bean이 다시 들어오면 **back edge = cycle** 검출.

- `DefaultSingletonBeanRegistry`의 `singletonsCurrentlyInCreation` Set이 바로 DFS 호출 스택.
- 운영 시 BeanCurrentlyInCreationException이 뜨면 → bean 의존성 그래프를 머릿속에 그리고 back edge를 찾는다. 보통 `@Lazy` 또는 setter injection으로 해결.

### 11.3 GC reachability marking

JVM GC의 핵심:

```
Mark phase = GC root(스택의 지역변수, static, JNI 등)에서 시작하여
             reachable한 객체를 DFS로 마킹.

Sweep/Compact phase = 마킹 안 된 객체를 회수.
```

- HotSpot의 Mark는 사실상 iterative DFS (heap 깊이가 깊을 수 있어서 explicit stack 사용).
- G1, ZGC, Shenandoah 모두 동일 — DFS marking + 영역별 회수.
- "GC 로그에서 mark phase가 길다" = **DFS가 도는 객체 그래프가 깊고 큼**. 깊은 객체 그래프(예: 거대한 linked list, deep nested cache)는 GC pause 늘림.

```
[Heap]
  root ──▶ A ──▶ B ──▶ C ──▶ D ──▶ ...
            │
            └──▶ E

GC mark = DFS(root) — 모든 reachable을 검은색으로 표시.
```

### 11.4 dependency graph cycle — Maven / Gradle

```
moduleA → moduleB → moduleA  ← cycle

→ Gradle: "Circular dependency between the following tasks/projects"
→ Maven: "The projects in the reactor contain a cyclic reference"
```

Build tool 내부에서 모듈/태스크 그래프에 DFS를 돌려 위상 정렬을 시도. 사이클이면 back edge 검출, build 실패. 운영자가 모듈을 늘려가다 갑자기 빌드가 깨지면 → DFS sketch부터 그린다.

### 11.5 분산 시스템의 distributed tracing

- 한 요청이 service A → B → C → D로 fan-out하는 호출 그래프 = DFS 트리.
- Jaeger / Zipkin 트레이스 뷰는 본질적으로 DFS span tree 시각화.
- 운영 시 "tail latency가 어디서 늘었나"를 보려면 trace tree의 post-order로 각 span 시간을 합쳐서 root까지 올림 → 트리 DP의 production 버전.

### 11.6 Database query plan tree

- RDBMS의 EXPLAIN 결과 = operator tree (LIMIT → SORT → JOIN → SCAN ...).
- 실행기는 이 트리를 DFS로 순회하며 결과를 위로 전달 (post-order).
- Postgres `EXPLAIN ANALYZE`의 "actual time" 합산은 post-order로 누적.

### 11.7 Tree shaking / dead code elimination

```
빌드 도구(webpack, esbuild, Rollup)는 entry → import graph를 DFS로 마킹.
마킹 안 된 모듈/함수 = dead code = 번들에서 제외.
```

본질은 GC의 mark phase와 같음. "compile-time GC".

### 11.8 Kubernetes controller reconcile

- Owner reference로 묶인 리소스 그래프 (Deployment → ReplicaSet → Pod)를 reconcile 시 DFS 또는 BFS로 순회.
- garbage collection of orphaned resources도 DFS marking 패턴.

---

## 12. 정리 — 백지 마스터 체크리스트

이 챕터를 백지에서 줄줄 풀려면 다음을 답할 수 있어야 한다.

1. DFS 인지 신호 8개 (섬, 모든 경로, 트리 깊이, 도달 가능, 컴포넌트, 사이클, 위상, 백트래킹 전 단계).
2. 재귀 호출 = JVM 콜 스택임을 그림으로.
3. visited 마킹 3가지 위치(case A/B/C) 차이.
4. 그리드 DFS Java 템플릿 외워서.
5. 그래프 DFS (인접 리스트) Java 템플릿.
6. 트리 DFS post-order로 자식 결과 집계 (LeetCode 543/124 패턴).
7. iterative DFS 변환 (Deque + 역순 push).
8. StackOverflowError 원인과 4가지 대비책.
9. DFS vs BFS 사용 시점.
10. DFS = Backtracking - 되돌리기.
11. DFS forest의 4종 edge.
12. Production 매핑: 디렉토리 walk, Spring DI 순환, GC marking, build tool cycle, trace tree.

이 12개가 백지에서 술술 나오면 DFS는 마스터.
