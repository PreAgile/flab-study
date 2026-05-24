# 09. BFS (Breadth-First Search)

> "BFS = 큐로 그래프 도는 거" 는 입문자. 시니어는 **"가중치 없는 그래프의 최단 거리"** 를 보장하는 유일한 선형 알고리즘이라는 점, visited 마킹을 **큐에 push하는 시점**에 해야 중복 방문이 막힌다는 점, **multi-source BFS** 로 N개의 출발점을 동시에 확산시키면 "각 칸에서 가장 가까운 출발점까지의 거리" 가 O(V+E)에 떨어진다는 것, **0-1 BFS** 는 deque의 head/tail을 가중치 0/1에 따라 갈라쳐 Dijkstra의 logV를 떼어낸다는 것을 본다.
>
> 이 챕터는 BFS를 백지에서 줄줄 그리고, multi-source / level-order / 0-1 / 양방향 변형까지 자유자재로 변주하며, 운영에서 K-hop 추천, traceroute, web crawler, Kubernetes pod fan-out에 어떻게 매핑되는지까지 묶는다.

---

## 0. 목차

1. 인지 신호 — BFS인지 30초에 분류하기
2. 백지 그리기 — 큐 확장·레벨 처리·multi-source·0-1·양방향
3. 직관과 정의 — DFS와의 핵심 차이, visited 마킹 시점
4. Java 템플릿 — 그리드 / 그래프 / multi-source / level
5. Kotlin 템플릿 — `ArrayDeque<IntArray>` 관용 표현
6. 시간·공간 복잡도
7. 대표 문제 6선 — 풀이·복잡도·함정까지
8. 함정·엣지케이스
9. 꼬리질문 트리 — 양방향·0-1·가중치·multi-source
10. 다른 패턴과의 연결 — DFS / Dijkstra / 트리 순회
11. 시니어 운영 매핑 — K-hop, traceroute, crawler, scheduler

---

## 1. 인지 신호 — 문제만 보고 BFS인지 30초에 분류

다음 키워드 중 **하나라도** 보이면 머릿속에서 큐를 꺼낸다.

| 키워드 / 신호 | 왜 BFS인가 |
|---|---|
| "최단 거리", "최소 단계", "최소 횟수" + **가중치 없음(=모든 edge 비용 동일)** | BFS는 가중치 0 또는 일정한 그래프의 최단 경로를 O(V+E)에 보장 |
| "레벨별 처리", "층별 출력", "K번째 깊이" | 큐 size를 캡처하면 한 레벨이 한 묶음으로 떨어짐 |
| "감염 확산", "불 번짐", "전염", "동시에 퍼지는" | multi-source BFS — 시작점을 모두 큐에 넣고 한 번에 확산 |
| "각 칸에서 가장 가까운 X까지의 거리" | multi-source BFS — X들을 출발점으로 |
| "단어 변환 사다리", "한 글자씩 바꾸기" | 상태 = 노드, 한 번의 변환 = edge 1 — BFS |
| "구슬 굴리기", "지뢰찾기", "체스 나이트 이동" | 격자 + 가중치 동일 = BFS |
| "친구의 친구 K단계까지" | K-hop BFS — level 단위 끊어 출력 |

**역신호 (BFS 아님)**:
- 가중치가 서로 다름 → Dijkstra / Bellman-Ford
- 음수 가중치 → Bellman-Ford / SPFA
- "모든 경로", "조합", "순열" → DFS / Backtracking
- 양 끝에서 좁혀오기 → Two Pointers
- 트리에서 깊이 우선 / 후위 처리 → DFS

> 핵심 한 줄: **"같은 한 걸음의 비용이 모두 같다"** + **"가장 적은 걸음 수"** = BFS.

---

## 2. 백지 그리기 — 5장면

### 2.1 큐 기반 단계별 확장

```
시작 노드 S 에서 BFS

      [S]
       │
   ┌───┼───┐
   A   B   C        ← 거리 1 (S 의 이웃)
  ┌┴┐ ┌┴┐ ┌┴┐
  D E F G H I       ← 거리 2 (이웃의 이웃)

큐 변화:
  init  Q=[S]              visited={S}
  pop S, push A,B,C        Q=[A,B,C]            d[A]=d[B]=d[C]=1
  pop A, push D,E          Q=[B,C,D,E]          d[D]=d[E]=2
  pop B, push F,G          Q=[C,D,E,F,G]        d[F]=d[G]=2
  pop C, push H,I          Q=[D,E,F,G,H,I]      d[H]=d[I]=2
  ...

불변식 (Invariant):
  큐 안에 있는 노드의 거리는 단조 증가하며, 차이는 최대 1.
  즉 Q = [d, d, d, ..., d, d+1, d+1, ...]  (앞은 d, 뒤는 d+1)
  → 그래서 처음 노드를 만난 순간 = 최단 거리.
```

### 2.2 레벨 처리 (size 캡처)

```
이진 트리 레벨 순회:

         1            ← level 0
       /   \
      2     3         ← level 1
     / \   / \
    4   5 6   7       ← level 2

큐 진행:
  Q=[1]
    size=1 → pop 1, push 2,3       level 0 = [1]
  Q=[2,3]
    size=2 → pop 2 push 4,5
            pop 3 push 6,7         level 1 = [2,3]
  Q=[4,5,6,7]
    size=4 → pop 4,5,6,7           level 2 = [4,5,6,7]

핵심 트릭:
  while (!q.isEmpty()) {
      int size = q.size();          ← ★ 이 시점에 size 캡처 ★
      for (int i = 0; i < size; i++) {
          Node cur = q.poll();
          ... process ...
          q.offer(child);
      }
      level++;
  }

size 를 캡처하지 않으면 새로 push한 자식까지 같이 처리해버려서
한 레벨씩 끊기지 않는다.
```

### 2.3 Multi-source BFS — 동시 확산

```
LeetCode 994 Rotting Oranges (썩은 오렌지 동시 확산)

초기 격자:                     큐 초기화:
 . R . F                       Q = [(0,1), (2,2)]
 F . F .                       모든 R 을 한 번에 큐에 push
 . F R .                       dist[(0,1)]=dist[(2,2)]=0

1 분 후 (큐에서 0인 것들 pop, 1로 마킹):
 R R R F                       두 출발점이 동시에 사방으로 1칸씩
 F R F R
 . R R R

2 분 후:
 R R R F                       (1,3) 의 F는 (2,3) 의 R에서 1분에 도달
 F R F R                       → 정답 2분
 R R R R

핵심: 시작점이 N개여도 큐에 한 번에 다 넣으면 "각 칸까지 가장 가까운
출발점에서의 거리" 가 한 번의 BFS로 구해진다.

만약 출발점마다 따로 BFS를 N번 돌리면 O(N · (V+E)).
multi-source BFS 는 그 자리에서 O(V+E).
```

### 2.4 0-1 BFS — Deque로 가중치 0/1 처리

```
edge 가중치가 0 또는 1만 있는 그래프 (예: "벽을 부수면 +1, 통로면 +0")

       0
   S ─────► A
   │ 1       │ 1
   ▼         ▼
   B ◄─────  C
       0

일반 BFS 는 못 씀 (가중치 다름).
Dijkstra 는 O((V+E) log V). overkill.

0-1 BFS:
  Deque 사용.
  edge 가중치 0 → addFirst (지금 거리 그대로)
  edge 가중치 1 → addLast  (지금 거리 + 1)

Deque 상태는 항상 [d, d, ..., d, d+1, d+1, ...] 단조 증가 유지.
pop 은 항상 front 에서 → 최소 거리 노드부터 처리 보장.

복잡도: O(V+E). Dijkstra 의 log V 가 사라진다.
```

### 2.5 양방향 BFS (Bidirectional BFS)

```
S 에서 T 까지 최단 경로. 분기 계수 b, 깊이 d.

단방향 BFS:    탐색 노드 ≈ b^d
양방향 BFS:    S 에서 d/2, T 에서 d/2 동시 → 2 · b^(d/2) = 2√(b^d)

   S ●─────────────────────● T
     ●─►●─►●           ●◄─●◄─●
        ↓                ↑
     앞쪽 BFS           뒤쪽 BFS
        프론티어가 만나는 순간 종료

조건:
  1. 시작과 끝이 모두 알려져 있어야 함
  2. 그래프가 무방향이거나, 역방향 edge 알 수 있어야 함

LeetCode 127 Word Ladder 가 대표 예. 사전 크기 5000, 단어 길이 10 일 때
단방향이면 26^L = 폭발하지만 양방향은 √만큼 줄어든다.
```

> 다섯 장면을 백지에 그대로 옮길 수 있어야 한다. 큐 상태 변화 / 레벨 size 캡처 / multi-source 동시 시작 / 0-1 BFS deque 갈라치기 / 양방향 프론티어 만남 — 이게 BFS 마스터의 기본기.

---

## 3. 직관과 정의

### 3.1 한 줄 비유

> **연못에 돌을 던지면 동심원이 퍼진다.** 그 동심원이 BFS다. 한 번에 한 겹씩 똑같은 두께로 퍼지므로, 어떤 점에 동심원이 처음 닿는 순간이 그 점까지의 최단 거리.

### 3.2 DFS와의 핵심 차이

| | DFS | BFS |
|---|---|---|
| 자료구조 | Stack (재귀 호출 스택 포함) | Queue |
| 탐색 순서 | 깊이 우선 — 한 길 끝까지 | 너비 우선 — 한 겹씩 |
| 최단 거리 보장 | ❌ 보장 못 함 | ✅ 가중치 동일 그래프에서 보장 |
| 메모리 | O(깊이) — 트리 균형 시 O(log N) | O(너비) — 트리에서 마지막 레벨 ≈ N/2 |
| 구현 | 재귀 (스택 오버플로 위험) | 반복 (큐 명시) |
| 사용처 | 모든 경로, 백트래킹, 위상정렬 | 최단 경로, 레벨 순회, 확산 |

**시험에 자주 나오는 함정**: "트리에서 BFS와 DFS 중 메모리 효율은?"
→ 완전 이진 트리에서 BFS는 마지막 레벨에 N/2 노드가 동시에 큐에 들어감.
DFS는 깊이 log N. 따라서 **DFS가 메모리에서 압도적 유리**.
그런데도 BFS를 쓰는 이유는 **최단 거리**가 필요할 때.

### 3.3 visited 마킹 시점 — 가장 자주 틀리는 부분

```
잘못된 코드 (pop 시점에 마킹):
  while (!q.isEmpty()) {
      int cur = q.poll();
      if (visited[cur]) continue;       ← pop 시점 체크
      visited[cur] = true;
      for (int next : adj[cur]) {
          q.offer(next);                ← 마킹 안 하고 push
      }
  }

문제: 같은 노드가 큐에 여러 번 들어감.
      예: A → B, A → C, B → D, C → D 면 D가 큐에 2번.
      → 큐 크기 폭발. 격자 BFS에서 4방향이면 큐가 4배.
      → TLE / MLE.

올바른 코드 (push 시점에 마킹):
  visited[start] = true;          ← 시작점부터 마킹
  q.offer(start);
  while (!q.isEmpty()) {
      int cur = q.poll();
      for (int next : adj[cur]) {
          if (visited[next]) continue;
          visited[next] = true;   ← ★ push 직전에 마킹 ★
          q.offer(next);
      }
  }

규칙: BFS의 visited는 push 시점, DFS의 visited는 pop(=진입) 시점.
정확히는 BFS는 "큐에 넣기로 결정한 순간 = 거리 확정 순간" 이므로
그 자리에서 막아야 중복 push가 안 생긴다.
```

### 3.4 정의 (수학적)

가중치 없는 그래프 `G=(V,E)` 와 시작 노드 `s` 에 대해 BFS는 다음을 O(V+E)에 계산한다:

- `dist[v]` = `s` 에서 `v` 까지의 최단 간선 개수 (도달 불가면 ∞)
- `parent[v]` = BFS 트리에서 `v` 의 부모 (역추적 시 경로 복원)

**증명 스케치**: 큐의 불변식 `Q = [d, d, ..., d, d+1, d+1, ...]` 에 의해 노드는 거리 비감소 순으로 pop 된다. 따라서 처음 큐에 들어가는 순간이 최단 거리. 귀납법으로 증명 가능.

---

## 4. Java 템플릿

### 4.1 그리드 BFS (4방향) — 가장 자주 쓰는 형태

```java
import java.util.*;

public class GridBFS {
    static final int[] DX = {-1, 1, 0, 0};
    static final int[] DY = {0, 0, -1, 1};

    public int shortestPath(int[][] grid, int sx, int sy, int tx, int ty) {
        int n = grid.length, m = grid[0].length;
        int[][] dist = new int[n][m];
        for (int[] row : dist) Arrays.fill(row, -1);

        Deque<int[]> q = new ArrayDeque<>();
        q.offer(new int[]{sx, sy});
        dist[sx][sy] = 0;

        while (!q.isEmpty()) {
            int[] cur = q.poll();
            int x = cur[0], y = cur[1];
            if (x == tx && y == ty) return dist[x][y];

            for (int d = 0; d < 4; d++) {
                int nx = x + DX[d];
                int ny = y + DY[d];
                if (nx < 0 || nx >= n || ny < 0 || ny >= m) continue;
                if (grid[nx][ny] == 0) continue;              // 벽
                if (dist[nx][ny] != -1) continue;             // 이미 방문
                dist[nx][ny] = dist[x][y] + 1;
                q.offer(new int[]{nx, ny});
            }
        }
        return -1;
    }
}
```

**암기 포인트**:
- `int[] DX, DY` 를 클래스 상수로 빼두면 4방향 / 8방향 변환 쉽다.
- `dist[][]` 가 visited 역할도 겸한다 (`-1` = 미방문).
- `dist != -1` 체크가 곧 push 시점 visited 마킹.
- `ArrayDeque` 가 `LinkedList` 보다 2~3배 빠르다 (Java 큐의 사실상 표준).

### 4.2 그래프 BFS (인접 리스트)

```java
public int[] bfs(List<List<Integer>> adj, int start) {
    int n = adj.size();
    int[] dist = new int[n];
    Arrays.fill(dist, -1);
    dist[start] = 0;

    Deque<Integer> q = new ArrayDeque<>();
    q.offer(start);

    while (!q.isEmpty()) {
        int cur = q.poll();
        for (int next : adj.get(cur)) {
            if (dist[next] != -1) continue;
            dist[next] = dist[cur] + 1;
            q.offer(next);
        }
    }
    return dist;
}
```

### 4.3 Multi-source BFS

```java
public int[][] multiSourceBFS(int[][] grid) {
    int n = grid.length, m = grid[0].length;
    int[][] dist = new int[n][m];
    for (int[] row : dist) Arrays.fill(row, -1);

    Deque<int[]> q = new ArrayDeque<>();

    // 모든 출발점을 한 번에 큐에 넣음 — 이게 multi-source의 핵심
    for (int i = 0; i < n; i++) {
        for (int j = 0; j < m; j++) {
            if (grid[i][j] == 1) {                // 출발점 (예: 썩은 오렌지)
                dist[i][j] = 0;
                q.offer(new int[]{i, j});
            }
        }
    }

    int[] DX = {-1, 1, 0, 0}, DY = {0, 0, -1, 1};

    while (!q.isEmpty()) {
        int[] cur = q.poll();
        int x = cur[0], y = cur[1];
        for (int d = 0; d < 4; d++) {
            int nx = x + DX[d], ny = y + DY[d];
            if (nx < 0 || nx >= n || ny < 0 || ny >= m) continue;
            if (dist[nx][ny] != -1) continue;
            if (grid[nx][ny] == -1) continue;     // 장애물
            dist[nx][ny] = dist[x][y] + 1;
            q.offer(new int[]{nx, ny});
        }
    }
    return dist;
}
```

**왜 한 번의 BFS로 모든 출발점에서의 최소 거리가 나오는가?**
- 큐의 불변식은 multi-source여도 동일하게 유지된다 (`[d, ..., d, d+1, ...]`).
- 어떤 칸이 처음 도달되는 시점이 **여러 출발점 중 가장 가까운** 거리.
- 가상의 super-source를 만들고 모든 출발점에 0-cost edge로 연결한 그래프에서의 BFS와 동치.

### 4.4 레벨 BFS (트리 레벨 순회)

```java
public List<List<Integer>> levelOrder(TreeNode root) {
    List<List<Integer>> result = new ArrayList<>();
    if (root == null) return result;

    Deque<TreeNode> q = new ArrayDeque<>();
    q.offer(root);

    while (!q.isEmpty()) {
        int size = q.size();                      // ★ size 캡처 ★
        List<Integer> level = new ArrayList<>();
        for (int i = 0; i < size; i++) {
            TreeNode cur = q.poll();
            level.add(cur.val);
            if (cur.left != null) q.offer(cur.left);
            if (cur.right != null) q.offer(cur.right);
        }
        result.add(level);
    }
    return result;
}
```

### 4.5 0-1 BFS

```java
public int zeroOneBFS(int n, List<int[]>[] adj, int start) {
    int[] dist = new int[n];
    Arrays.fill(dist, Integer.MAX_VALUE);
    dist[start] = 0;

    Deque<Integer> dq = new ArrayDeque<>();
    dq.offerFirst(start);

    while (!dq.isEmpty()) {
        int cur = dq.pollFirst();
        for (int[] e : adj[cur]) {
            int next = e[0], w = e[1];            // w ∈ {0, 1}
            if (dist[cur] + w < dist[next]) {
                dist[next] = dist[cur] + w;
                if (w == 0) dq.offerFirst(next);  // 비용 0 → 앞에
                else        dq.offerLast(next);   // 비용 1 → 뒤에
            }
        }
    }
    return dist[n - 1];
}
```

### 4.6 양방향 BFS (사전 단어 변환 같은 상태 그래프)

```java
public int bidirectionalBFS(String beginWord, String endWord, Set<String> dict) {
    if (!dict.contains(endWord)) return 0;
    Set<String> front = new HashSet<>(), back = new HashSet<>(), visited = new HashSet<>();
    front.add(beginWord);
    back.add(endWord);
    int steps = 1;

    while (!front.isEmpty() && !back.isEmpty()) {
        if (front.size() > back.size()) {         // 작은 쪽에서 확장 (균형)
            Set<String> tmp = front; front = back; back = tmp;
        }
        Set<String> next = new HashSet<>();
        for (String word : front) {
            char[] chars = word.toCharArray();
            for (int i = 0; i < chars.length; i++) {
                char old = chars[i];
                for (char c = 'a'; c <= 'z'; c++) {
                    chars[i] = c;
                    String nw = new String(chars);
                    if (back.contains(nw)) return steps + 1;
                    if (dict.contains(nw) && !visited.contains(nw)) {
                        next.add(nw);
                        visited.add(nw);
                    }
                }
                chars[i] = old;
            }
        }
        front = next;
        steps++;
    }
    return 0;
}
```

---

## 5. Kotlin 템플릿

### 5.1 그리드 BFS

```kotlin
import java.util.ArrayDeque

class GridBFS {
    private val dx = intArrayOf(-1, 1, 0, 0)
    private val dy = intArrayOf(0, 0, -1, 1)

    fun shortestPath(grid: Array<IntArray>, sx: Int, sy: Int, tx: Int, ty: Int): Int {
        val n = grid.size
        val m = grid[0].size
        val dist = Array(n) { IntArray(m) { -1 } }

        val q: ArrayDeque<IntArray> = ArrayDeque()
        q.offer(intArrayOf(sx, sy))
        dist[sx][sy] = 0

        while (q.isNotEmpty()) {
            val (x, y) = q.poll()
            if (x == tx && y == ty) return dist[x][y]
            for (d in 0 until 4) {
                val nx = x + dx[d]
                val ny = y + dy[d]
                if (nx !in 0 until n || ny !in 0 until m) continue
                if (grid[nx][ny] == 0) continue
                if (dist[nx][ny] != -1) continue
                dist[nx][ny] = dist[x][y] + 1
                q.offer(intArrayOf(nx, ny))
            }
        }
        return -1
    }
}
```

Kotlin 관용 표현:
- `val (x, y) = q.poll()` 의 destructuring — `IntArray` 도 `component1/2` 가 안 되니까 `intArrayOf` 면 직접 인덱싱하거나 `Pair` 사용. 위 코드는 `IntArray` destructuring을 위해 확장 함수 정의가 필요할 수 있어 `val cur = q.poll(); val x = cur[0]; val y = cur[1]` 가 더 안전.

수정본:

```kotlin
while (q.isNotEmpty()) {
    val cur = q.poll()
    val x = cur[0]; val y = cur[1]
    if (x == tx && y == ty) return dist[x][y]
    for (d in 0 until 4) {
        val nx = x + dx[d]
        val ny = y + dy[d]
        if (nx !in 0 until n || ny !in 0 until m) continue
        if (grid[nx][ny] == 0) continue
        if (dist[nx][ny] != -1) continue
        dist[nx][ny] = dist[x][y] + 1
        q.offer(intArrayOf(nx, ny))
    }
}
```

### 5.2 Multi-source BFS

```kotlin
fun multiSourceBFS(grid: Array<IntArray>): Array<IntArray> {
    val n = grid.size
    val m = grid[0].size
    val dist = Array(n) { IntArray(m) { -1 } }
    val q: ArrayDeque<IntArray> = ArrayDeque()

    for (i in 0 until n) for (j in 0 until m) {
        if (grid[i][j] == 1) {
            dist[i][j] = 0
            q.offer(intArrayOf(i, j))
        }
    }

    val dx = intArrayOf(-1, 1, 0, 0)
    val dy = intArrayOf(0, 0, -1, 1)

    while (q.isNotEmpty()) {
        val cur = q.poll()
        val x = cur[0]; val y = cur[1]
        for (d in 0 until 4) {
            val nx = x + dx[d]; val ny = y + dy[d]
            if (nx !in 0 until n || ny !in 0 until m) continue
            if (dist[nx][ny] != -1) continue
            if (grid[nx][ny] == -1) continue
            dist[nx][ny] = dist[x][y] + 1
            q.offer(intArrayOf(nx, ny))
        }
    }
    return dist
}
```

### 5.3 레벨 BFS (트리)

```kotlin
fun levelOrder(root: TreeNode?): List<List<Int>> {
    val result = mutableListOf<List<Int>>()
    if (root == null) return result
    val q: ArrayDeque<TreeNode> = ArrayDeque()
    q.offer(root)

    while (q.isNotEmpty()) {
        val size = q.size
        val level = mutableListOf<Int>()
        repeat(size) {
            val cur = q.poll()
            level.add(cur.`val`)
            cur.left?.let { q.offer(it) }
            cur.right?.let { q.offer(it) }
        }
        result.add(level)
    }
    return result
}
```

---

## 6. 시간·공간 복잡도

| 항목 | 값 | 근거 |
|---|---|---|
| 시간 (그래프) | O(V + E) | 각 정점은 큐에 한 번 들어가고 한 번 나옴, 각 간선은 한 번씩 검사 |
| 시간 (격자 N×M) | O(N·M) | 정점 N·M개, 4방향 간선 = 4·N·M = O(N·M) |
| 공간 (큐 최대 크기) | O(V) — 최악 O(V), 평균 O(너비 분기 계수^d) | 트리에서 마지막 레벨이 큐를 가득 채움 |
| 공간 (visited / dist) | O(V) | 정점당 1바이트 또는 1int |

### 6.1 큐 메모리 폭발 예시 — 자주 만나는 함정

```
완전 이진 트리, 깊이 d:
  - 정점 수 = 2^(d+1) - 1
  - 마지막 레벨 노드 수 = 2^d ≈ N/2
  - BFS 큐 최대 크기 = 2^d ≈ N/2
  - DFS 스택 최대 크기 = d ≈ log N

격자 1000 × 1000:
  - 정점 수 = 10^6
  - 큐 최대 크기 ≈ 4000 (대각선 경계, b·O(√N))
  - int[2] 객체 1개 ≈ 24 byte (header 16 + data 8) + 배열 헤더 16 = 40 byte
  - 큐 4000개 ≈ 160 KB. OK.
  - 큐 10^7개면 400 MB → OOM.

→ 입력 크기 × b (분기 계수) 추정 후 메모리 짚어야 한다.
```

### 6.2 Dijkstra와의 복잡도 차이

| | BFS | Dijkstra |
|---|---|---|
| 시간 | O(V + E) | O((V + E) log V) (binary heap) |
| 전제 | 가중치 동일 (또는 없음) | 가중치 비음수 |
| 자료구조 | 큐 | 우선순위 큐 (힙) |

> 모든 가중치가 같으면 Dijkstra = BFS. BFS는 Dijkstra의 특수화. **굳이 가중치가 같은 그래프에 Dijkstra 쓰면 log V만큼 낭비** — 면접관이 짚는다.

---

## 7. 대표 문제 6선

### 7.1 LeetCode 102 — Binary Tree Level Order Traversal

**문제**: 이진 트리의 노드를 레벨별로 묶어서 리스트로 반환.

**접근**: 큐 size 캡처로 한 레벨씩 끊는다.

**Java**:

```java
public List<List<Integer>> levelOrder(TreeNode root) {
    List<List<Integer>> result = new ArrayList<>();
    if (root == null) return result;
    Deque<TreeNode> q = new ArrayDeque<>();
    q.offer(root);
    while (!q.isEmpty()) {
        int size = q.size();
        List<Integer> level = new ArrayList<>(size);
        for (int i = 0; i < size; i++) {
            TreeNode cur = q.poll();
            level.add(cur.val);
            if (cur.left != null) q.offer(cur.left);
            if (cur.right != null) q.offer(cur.right);
        }
        result.add(level);
    }
    return result;
}
```

**Kotlin**:

```kotlin
fun levelOrder(root: TreeNode?): List<List<Int>> {
    val result = mutableListOf<List<Int>>()
    if (root == null) return result
    val q: ArrayDeque<TreeNode> = ArrayDeque()
    q.offer(root)
    while (q.isNotEmpty()) {
        val size = q.size
        val level = ArrayList<Int>(size)
        repeat(size) {
            val cur = q.poll()
            level.add(cur.`val`)
            cur.left?.let { q.offer(it) }
            cur.right?.let { q.offer(it) }
        }
        result.add(level)
    }
    return result
}
```

**복잡도**: 시간 O(N), 공간 O(N) (마지막 레벨 큐 크기 ≈ N/2).

**함정**:
- `size` 를 캡처하지 않고 `while (!q.isEmpty())` 만 돌면 한 줄 출력으로 합쳐진다.
- `null` 체크를 `q.offer` 전에 안 하면 큐에 `null` 이 들어가 NPE.

**변형**:
- Zigzag (107/103): `level` 을 짝/홀수에 따라 reverse.
- Right-side view (199): 각 레벨의 마지막 원소만 추출.
- Average of levels (637): 각 레벨의 평균.

---

### 7.2 LeetCode 994 — Rotting Oranges (Multi-source BFS)

**문제**: 격자에 신선한 오렌지(1)와 썩은 오렌지(2)가 있다. 매 분마다 썩은 오렌지의 4방향 인접 신선 오렌지가 같이 썩는다. 모든 오렌지가 썩는 데 걸리는 최소 시간을 구하라. 불가능하면 -1.

**접근**: 모든 썩은 오렌지를 동시에 큐에 넣고 한 번의 BFS. 마지막에 신선 오렌지가 남으면 -1.

**Java**:

```java
public int orangesRotting(int[][] grid) {
    int n = grid.length, m = grid[0].length;
    Deque<int[]> q = new ArrayDeque<>();
    int fresh = 0;
    for (int i = 0; i < n; i++) {
        for (int j = 0; j < m; j++) {
            if (grid[i][j] == 2) q.offer(new int[]{i, j, 0});
            else if (grid[i][j] == 1) fresh++;
        }
    }
    if (fresh == 0) return 0;

    int[] DX = {-1, 1, 0, 0}, DY = {0, 0, -1, 1};
    int minutes = 0;
    while (!q.isEmpty()) {
        int[] cur = q.poll();
        int x = cur[0], y = cur[1], t = cur[2];
        minutes = t;
        for (int d = 0; d < 4; d++) {
            int nx = x + DX[d], ny = y + DY[d];
            if (nx < 0 || nx >= n || ny < 0 || ny >= m) continue;
            if (grid[nx][ny] != 1) continue;
            grid[nx][ny] = 2;                    // ★ push 시점 마킹 (visited 역할)
            fresh--;
            q.offer(new int[]{nx, ny, t + 1});
        }
    }
    return fresh == 0 ? minutes : -1;
}
```

**Kotlin**:

```kotlin
fun orangesRotting(grid: Array<IntArray>): Int {
    val n = grid.size; val m = grid[0].size
    val q: ArrayDeque<IntArray> = ArrayDeque()
    var fresh = 0
    for (i in 0 until n) for (j in 0 until m) {
        if (grid[i][j] == 2) q.offer(intArrayOf(i, j, 0))
        else if (grid[i][j] == 1) fresh++
    }
    if (fresh == 0) return 0

    val dx = intArrayOf(-1, 1, 0, 0); val dy = intArrayOf(0, 0, -1, 1)
    var minutes = 0
    while (q.isNotEmpty()) {
        val cur = q.poll()
        val x = cur[0]; val y = cur[1]; val t = cur[2]
        minutes = t
        for (d in 0 until 4) {
            val nx = x + dx[d]; val ny = y + dy[d]
            if (nx !in 0 until n || ny !in 0 until m) continue
            if (grid[nx][ny] != 1) continue
            grid[nx][ny] = 2
            fresh--
            q.offer(intArrayOf(nx, ny, t + 1))
        }
    }
    return if (fresh == 0) minutes else -1
}
```

**복잡도**: O(N·M).

**함정**:
- `fresh == 0` 초기 체크를 빠뜨리면 모든 칸이 비어도 답이 0이 아니라 잘못 나옴.
- BFS 끝나고 신선이 남아 있으면 도달 불가 → -1.
- 시간을 큐에 담는 대신 level 사이즈 캡처 방식으로도 가능. 두 방법 모두 외워둘 것.

**왜 multi-source인가**: 출발점이 N개여도 한 번의 BFS면 모든 도착점까지의 거리가 정확히 "가장 가까운 출발점까지의 거리" 가 된다. N번 BFS 돌리면 O(N²·M) → O(N·M).

---

### 7.3 LeetCode 542 — 01 Matrix (Multi-source BFS의 정수)

**문제**: 0과 1로 이루어진 격자에서 각 1 셀에 대해 가장 가까운 0 셀까지의 거리를 구하라.

**Naive**: 각 1에서 BFS → O((N·M)²). MLE/TLE.

**핵심 통찰**: **0들을 모두 출발점으로** 잡고 multi-source BFS. 그러면 한 번의 BFS로 모든 1까지의 최단 거리가 나온다.

**Java**:

```java
public int[][] updateMatrix(int[][] mat) {
    int n = mat.length, m = mat[0].length;
    int[][] dist = new int[n][m];
    for (int[] row : dist) Arrays.fill(row, -1);

    Deque<int[]> q = new ArrayDeque<>();
    for (int i = 0; i < n; i++) {
        for (int j = 0; j < m; j++) {
            if (mat[i][j] == 0) {
                dist[i][j] = 0;
                q.offer(new int[]{i, j});
            }
        }
    }

    int[] DX = {-1, 1, 0, 0}, DY = {0, 0, -1, 1};
    while (!q.isEmpty()) {
        int[] cur = q.poll();
        int x = cur[0], y = cur[1];
        for (int d = 0; d < 4; d++) {
            int nx = x + DX[d], ny = y + DY[d];
            if (nx < 0 || nx >= n || ny < 0 || ny >= m) continue;
            if (dist[nx][ny] != -1) continue;
            dist[nx][ny] = dist[x][y] + 1;
            q.offer(new int[]{nx, ny});
        }
    }
    return dist;
}
```

**Kotlin**:

```kotlin
fun updateMatrix(mat: Array<IntArray>): Array<IntArray> {
    val n = mat.size; val m = mat[0].size
    val dist = Array(n) { IntArray(m) { -1 } }
    val q: ArrayDeque<IntArray> = ArrayDeque()
    for (i in 0 until n) for (j in 0 until m) {
        if (mat[i][j] == 0) { dist[i][j] = 0; q.offer(intArrayOf(i, j)) }
    }
    val dx = intArrayOf(-1, 1, 0, 0); val dy = intArrayOf(0, 0, -1, 1)
    while (q.isNotEmpty()) {
        val cur = q.poll(); val x = cur[0]; val y = cur[1]
        for (d in 0 until 4) {
            val nx = x + dx[d]; val ny = y + dy[d]
            if (nx !in 0 until n || ny !in 0 until m) continue
            if (dist[nx][ny] != -1) continue
            dist[nx][ny] = dist[x][y] + 1
            q.offer(intArrayOf(nx, ny))
        }
    }
    return dist
}
```

**복잡도**: O(N·M).

**함정**:
- "1을 출발점으로" 하면 잘못된 답이 나옴. 왜냐하면 "각 1에서 가장 가까운 0" 이 답이지, "각 0에서 가장 가까운 1" 이 아니다. 그런데 거리 함수는 대칭이라 0을 출발점으로 잡아도 정확히 같은 답이 나옴. 0이 보통 더 많거나 적거나 어쨌든 출발점이 더 적은 쪽이 큐 크기 절약.

---

### 7.4 LeetCode 286 — Walls and Gates (Multi-source BFS)

**문제**: 격자에 벽(-1), 방(INF), 문(0)이 있다. 각 방에 가장 가까운 문까지의 거리를 채워라.

**접근**: 문들을 모두 출발점으로 multi-source BFS.

**Java**:

```java
public void wallsAndGates(int[][] rooms) {
    int n = rooms.length, m = rooms[0].length;
    Deque<int[]> q = new ArrayDeque<>();
    for (int i = 0; i < n; i++) {
        for (int j = 0; j < m; j++) {
            if (rooms[i][j] == 0) q.offer(new int[]{i, j});
        }
    }
    int[] DX = {-1, 1, 0, 0}, DY = {0, 0, -1, 1};
    while (!q.isEmpty()) {
        int[] cur = q.poll();
        int x = cur[0], y = cur[1];
        for (int d = 0; d < 4; d++) {
            int nx = x + DX[d], ny = y + DY[d];
            if (nx < 0 || nx >= n || ny < 0 || ny >= m) continue;
            if (rooms[nx][ny] != Integer.MAX_VALUE) continue;   // 벽 또는 이미 방문
            rooms[nx][ny] = rooms[x][y] + 1;
            q.offer(new int[]{nx, ny});
        }
    }
}
```

**Kotlin**:

```kotlin
fun wallsAndGates(rooms: Array<IntArray>) {
    val n = rooms.size; val m = rooms[0].size
    val q: ArrayDeque<IntArray> = ArrayDeque()
    for (i in 0 until n) for (j in 0 until m) {
        if (rooms[i][j] == 0) q.offer(intArrayOf(i, j))
    }
    val dx = intArrayOf(-1, 1, 0, 0); val dy = intArrayOf(0, 0, -1, 1)
    while (q.isNotEmpty()) {
        val cur = q.poll(); val x = cur[0]; val y = cur[1]
        for (d in 0 until 4) {
            val nx = x + dx[d]; val ny = y + dy[d]
            if (nx !in 0 until n || ny !in 0 until m) continue
            if (rooms[nx][ny] != Int.MAX_VALUE) continue
            rooms[nx][ny] = rooms[x][y] + 1
            q.offer(intArrayOf(nx, ny))
        }
    }
}
```

**복잡도**: O(N·M).

**함정**:
- `INF` 만 갱신 가능하다는 조건이 visited 마킹 역할까지 한다. 별도 visited 배열 불필요.
- 벽(-1)도 `!= INF` 에 걸려 자연스럽게 차단.

---

### 7.5 LeetCode 127 — Word Ladder (양방향 BFS)

**문제**: `beginWord` 에서 `endWord` 로 한 글자씩 바꿔가며 도달. 매 단계 단어는 사전(`wordList`)에 있어야 함. 최단 변환 길이는?

**접근**:
- 상태 = 단어, edge = 한 글자 차이.
- 단방향 BFS: 사전 크기 N, 단어 길이 L → O(N·L²) (글자 26개 시도 + 단어 비교 L).
- 양방향 BFS: 단방향의 √만큼 줄어듦. 5000 단어, L=10 에서 차이가 압도적.

**Java (양방향)**: 4.6의 템플릿이 그대로 답.

**Kotlin (단방향, 간결)**:

```kotlin
fun ladderLength(beginWord: String, endWord: String, wordList: List<String>): Int {
    val dict = wordList.toHashSet()
    if (endWord !in dict) return 0
    val q: ArrayDeque<String> = ArrayDeque()
    q.offer(beginWord)
    val visited = HashSet<String>().apply { add(beginWord) }
    var steps = 1
    while (q.isNotEmpty()) {
        val size = q.size
        repeat(size) {
            val word = q.poll()
            if (word == endWord) return steps
            val chars = word.toCharArray()
            for (i in chars.indices) {
                val old = chars[i]
                for (c in 'a'..'z') {
                    chars[i] = c
                    val nw = String(chars)
                    if (nw in dict && nw !in visited) {
                        visited.add(nw)
                        q.offer(nw)
                    }
                }
                chars[i] = old
            }
        }
        steps++
    }
    return 0
}
```

**복잡도**: 단방향 O(N·L²·26), 양방향 O(√(N·L²·26)).

**함정**:
- `wordList` 를 `Set` 으로 바꾸지 않으면 `contains` 가 O(N) — 전체가 O(N²·L²) 로 폭발.
- `beginWord` 자체는 사전에 없어도 OK. `endWord` 는 반드시 사전에 있어야 함.
- 양방향 BFS 에서 `front`/`back` 중 **작은 쪽을 확장**해야 균형이 깨지지 않는다.

---

### 7.6 프로그래머스 — 게임 맵 최단거리

**문제**: N×M 격자에서 (0,0) → (N-1, M-1) 최단 거리. 1=통로, 0=벽. 도달 불가 시 -1.

그리드 BFS의 정석. 미로 탐색 기본형이며, 시작 칸을 거리 1로 두어 "칸 수" 를 센다 (단계 수가 아님).

**Java**:

```java
class Solution {
    public int solution(int[][] maps) {
        int n = maps.length, m = maps[0].length;
        int[][] dist = new int[n][m];
        for (int[] row : dist) java.util.Arrays.fill(row, -1);

        java.util.Deque<int[]> q = new java.util.ArrayDeque<>();
        q.offer(new int[]{0, 0});
        dist[0][0] = 1;

        int[] DX = {-1, 1, 0, 0}, DY = {0, 0, -1, 1};
        while (!q.isEmpty()) {
            int[] cur = q.poll();
            int x = cur[0], y = cur[1];
            if (x == n - 1 && y == m - 1) return dist[x][y];
            for (int d = 0; d < 4; d++) {
                int nx = x + DX[d], ny = y + DY[d];
                if (nx < 0 || nx >= n || ny < 0 || ny >= m) continue;
                if (maps[nx][ny] == 0) continue;
                if (dist[nx][ny] != -1) continue;
                dist[nx][ny] = dist[x][y] + 1;
                q.offer(new int[]{nx, ny});
            }
        }
        return -1;
    }
}
```

**Kotlin**:

```kotlin
class Solution {
    fun solution(maps: Array<IntArray>): Int {
        val n = maps.size; val m = maps[0].size
        val dist = Array(n) { IntArray(m) { -1 } }
        val q: ArrayDeque<IntArray> = ArrayDeque()
        q.offer(intArrayOf(0, 0))
        dist[0][0] = 1
        val dx = intArrayOf(-1, 1, 0, 0); val dy = intArrayOf(0, 0, -1, 1)
        while (q.isNotEmpty()) {
            val cur = q.poll(); val x = cur[0]; val y = cur[1]
            if (x == n - 1 && y == m - 1) return dist[x][y]
            for (d in 0 until 4) {
                val nx = x + dx[d]; val ny = y + dy[d]
                if (nx !in 0 until n || ny !in 0 until m) continue
                if (maps[nx][ny] == 0) continue
                if (dist[nx][ny] != -1) continue
                dist[nx][ny] = dist[x][y] + 1
                q.offer(intArrayOf(nx, ny))
            }
        }
        return -1
    }
}
```

---

## 8. 함정·엣지케이스 — 면접관이 짚는 포인트

### 8.1 visited 마킹 위치 — 가장 흔한 버그

```
잘못: pop 시점에 마킹
  → 같은 노드가 큐에 여러 번. 큐 크기 O(V²) 까지 폭발.
  → 격자 4방향이면 큐 크기가 4× 증가 → MLE.

올바름: push 시점에 마킹 (또는 dist[next] != -1 체크)
  → 큐에 정확히 한 번씩 → O(V) 보장.
```

### 8.2 시작 노드 다중 — multi-source 인식 실패

```
문제: "각 칸에서 가장 가까운 X까지의 거리"
잘못된 접근: 각 칸에서 BFS → O(N²·M²)
올바른 접근: X들 전부를 출발점으로 multi-source BFS → O(N·M)

신호: "각 점에서 가장 가까운 _____" → multi-source 의심
```

### 8.3 큐 메모리 폭발

```
1000 × 1000 격자, 4방향 BFS:
  - int[2] 박싱: 객체 + 배열 헤더 ≈ 40 byte
  - 10^6 칸 × 40 byte = 40 MB. 보통 OK.

10^6 × 10 차원 상태 BFS:
  - 10^7 객체 × 40 byte = 400 MB. OOM.

대책: 상태를 int 한 개로 인코딩 (예: x * M + y).
      또는 두 차원을 별도 IntArray 로.
```

### 8.4 dx/dy 배열 누락 / 8방향 헷갈림

```
4방향:  dx = {-1, 1, 0, 0},  dy = {0, 0, -1, 1}
8방향:  dx = {-1,-1,-1, 0, 0, 1, 1, 1}
        dy = {-1, 0, 1,-1, 1,-1, 0, 1}

체스 나이트:
  dx = {-2,-2,-1,-1, 1, 1, 2, 2}
  dy = {-1, 1,-2, 2,-2, 2,-1, 1}

문제 읽고 어떤 이동인지 즉시 dx/dy 정의하고 시작할 것.
"대각선 포함?" 을 면접관에게 묻는 습관.
```

### 8.5 거리 초기값 — 0 vs 1

```
"몇 단계 이동했는가?"  → dist[start] = 0
"몇 칸을 거쳤는가?"   → dist[start] = 1 (시작 칸 포함)

프로그래머스 게임 맵 최단거리 = 칸 수 → 1 부터.
LeetCode 1091 = 단계 수 → 1 부터 (시작 칸도 길이에 포함).
대부분의 그래프 최단 경로 = 단계 수 → 0 부터.

엣지 케이스: start == target 일 때 0인가 1인가? 문제 정의 확인.
```

### 8.6 격자가 아닌 그래프 — 자기 자신 루프 / 다중 간선

```
인접 리스트가 self-loop 나 중복 간선을 가지면 visited 체크 없으면 무한 루프.
무조건 push 직전 visited 체크.

방향 그래프인데 BFS 로 최단 거리: edge 방향 지켜야 함.
무방향이면 양쪽 다 push.
```

### 8.7 단방향 vs 양방향 BFS 선택

```
양방향 BFS 조건:
  1. 시작·끝 모두 알려져 있음
  2. 무방향 또는 역방향 edge 알 수 있음
  3. 분기 계수 b 와 깊이 d 가 커서 b^(d/2) << b^d

만족 안 되면 단방향. Word Ladder, 8-puzzle 은 양방향 큰 효과.
일반 그리드 BFS 는 b=4, d 작아서 양방향 효과 미미.
```

---

## 9. 꼬리질문 트리

### 9.1 "더 빠르게 — 양방향 BFS?"

> 양방향 BFS는 분기 계수 b, 깊이 d 일 때 b^d 를 2·b^(d/2) 로 줄인다. 즉 √만큼 줄어든다. 시작·끝이 모두 알려져 있고 역방향 탐색이 가능할 때만 적용. Word Ladder, 8-puzzle, 사회망 6단계 분리 같은 큰 b·d 상황에서 효과 큼. 일반 격자 BFS 는 효과 미미.

### 9.2 "가중치가 0 또는 1만 있으면 — 0-1 BFS?"

> Dijkstra 의 log V를 떼어내고 O(V+E) 로 풀 수 있다. deque 를 써서 0-edge 는 addFirst, 1-edge 는 addLast. deque 의 거리 단조성은 유지된다. "벽을 K번까지 부수면서 최단 경로" 같은 문제에 즉시 적용.

### 9.3 "왜 BFS 로 가중치 있는 그래프 최단 경로를 못 푸는가?"

> BFS 의 정당성은 큐의 불변식 `Q = [d, ..., d, d+1, ...]` 에 의존. 가중치가 다르면 한 노드를 일찍 pop 했는데 나중에 더 짧은 경로가 발견될 수 있어 불변식이 깨진다. 그래서 Dijkstra (heap), 음수 있으면 Bellman-Ford / SPFA 가 필요.

### 9.4 "Multi-source BFS 의 활용?"

> "각 점에서 가장 가까운 X까지의 거리" 유형 전부. LeetCode 542, 994, 286, 1162 (Shortest Distance from All Buildings 의 역) 등. **운영 매핑**: Kubernetes node 와 pod 사이 "가장 가까운 readiness probe 가 통과한 pod" 같은 다대다 최단 거리. CDN의 "각 사용자에서 가장 가까운 edge node" 도 동일 구조.

### 9.5 "BFS 메모리가 부담스러우면?"

> Iterative Deepening DFS (IDDFS). DFS 의 메모리 O(d) 와 BFS 의 최단 거리 보장을 결합. depth 1, 2, 3, ... 으로 DFS 를 반복. 총 비용은 b^d (BFS 와 동급) 지만 메모리는 O(d). AlphaBeta search, 미니맥스 에서 자주 등장.

### 9.6 "트리에서 BFS 인 게 의미 있는가?"

> 트리는 cycle 이 없어 visited 가 불필요. BFS 는 레벨 순회 (102, 199, 637, 116 등)에서 핵심. 그래프 BFS 와 코드 구조는 같지만 visited 가 빠진다는 점만 다르다.

### 9.7 "양방향 BFS 에서 만나는 시점을 어떻게 감지하나?"

> 각 BFS 가 자기 visited 셋과 거리 맵을 가지고 있다가, 새 노드가 다른 쪽 visited 셋에 있으면 만난 것. 거리 = `dist_front + dist_back`. 단, 두 BFS가 동시에 같은 노드를 push 하면 만남으로 처리해야 누락이 안 된다.

### 9.8 "Distributed BFS — 그래프가 분산 저장이라면?"

> Pregel / GraphX / GraphFrames 의 BSP (Bulk Synchronous Parallel) 모델. 각 노드가 한 super-step 에 자기 이웃에게 메시지 전송, 다음 step 에 수신. step 수가 BFS 깊이. PageRank 와 동일한 인프라. 운영: 페이스북 친구 추천이 이 구조.

---

## 10. 다른 패턴과의 연결

### 10.1 DFS 와의 관계 — 자료구조 한 줄 차이

```
BFS: Queue (FIFO)
DFS: Stack (LIFO, 또는 재귀)

자료구조만 바꾸면 같은 코드.

void traverse(int start) {
    var frontier = ???;             // ArrayDeque or Stack
    frontier.add(start);
    visited.add(start);
    while (!frontier.isEmpty()) {
        var cur = frontier.removeFirst();   // BFS: poll
                                            // DFS: pop
        for (int next : adj[cur]) {
            if (visited.contains(next)) continue;
            visited.add(next);
            frontier.add(next);
        }
    }
}
```

용도:
- 모든 경로 / 백트래킹 / 위상정렬 → DFS
- 최단 거리 / 레벨 처리 / 확산 → BFS

### 10.2 Dijkstra 와의 관계

```
Dijkstra = BFS 의 일반화. 큐 대신 우선순위 큐.
모든 edge 가 같은 비용이면 Dijkstra = BFS (큐가 PQ가 되어도 같은 순서).

따라서:
- 가중치 같음 → BFS (O(V+E))
- 가중치 0/1  → 0-1 BFS (O(V+E), deque)
- 가중치 양수 → Dijkstra (O((V+E) log V))
- 음수 가중치 → Bellman-Ford (O(VE))

이 사다리를 외워두면 면접에서 "왜 BFS?" 에 즉답.
```

### 10.3 트리 레벨 순회와의 관계

```
이진 트리 레벨 순회 = BFS + size 캡처
이 패턴이 그대로 다음으로 확장:
  - Level Order Traversal (102)
  - Zigzag Level Order (103)
  - Right-side View (199)
  - Average of Levels (637)
  - Populating Next Right Pointer (116, 117)
  - Find Largest Value in Each Tree Row (515)

전부 "size 캡처 + 레벨별 처리" 의 변주.
```

### 10.4 Union-Find 와의 관계

```
"연결 컴포넌트 개수" 같은 문제는 BFS / DFS / Union-Find 모두 가능.

BFS/DFS:        O(V+E), 그래프 한 번 순회.
Union-Find:    O(α(V)·E), 동적으로 edge 추가될 때 강함.

오프라인 (그래프 고정) → BFS/DFS.
온라인 (edge 동적 추가) → Union-Find.
```

### 10.5 Topological Sort (Kahn's algorithm) — BFS 의 응용

```
Kahn's: in-degree 0 인 노드를 큐에 넣고 BFS.
        pop 하면 결과에 추가, 그 노드의 out-edge 제거, 새로 in-degree 0 된 노드 push.
        결과 길이 < V 면 cycle 존재.

이것도 본질은 BFS. "위상정렬 = in-degree 기반 BFS" 라고 외워둘 것.
```

---

## 11. 시니어 운영 매핑 — 이 지식이 production 에서 어디 쓰이나

### 11.1 소셜 네트워크 K-hop 추천 — "친구의 친구"

```
페이스북 / 링크드인 "친구 추천" = K-hop BFS
  사용자 u 에서 BFS, 거리 2~3 노드를 추천.
  사용자 1억, 평균 친구 200명 → 2-hop = 40,000 후보. 3-hop = 800만. 분산 BFS 필수.

구현:
  - Pregel / GraphX BSP
  - 각 super-step 이 BFS 한 단계
  - frontier 가 큐 대신 분산 메시지
  - 큰 노드 (셀럽, 친구 수 100만)는 별도 처리 (skewed partition)

면접관 질문: "10억 노드에서 어떻게 K-hop 을 하나?"
답: 분산 BFS + 메시지 패싱 + skewed node 별도 처리 + early termination (이미 추천 1000개 모이면 멈춤).
```

### 11.2 Traceroute / 네트워크 진단

```
traceroute 는 TTL 을 1, 2, 3... 으로 증가시키며 ICMP TIME EXCEEDED 를 받음.
이게 본질적으로 BFS 의 레벨별 확장.

각 TTL = BFS 한 레벨. ICMP 응답 = 그 레벨의 노드 식별.

이상 진단:
  - 특정 레벨에서 응답 누락 → 라우터 ICMP 차단 또는 장애
  - 같은 레벨이 여러 IP → ECMP (Equal-Cost Multi-Path), 패킷마다 다른 경로
  - latency 가 특정 레벨에서 점프 → 해당 hop 이 병목
```

### 11.3 Web Crawler

```
Crawler 는 BFS 의 정수.
  Seed URL → 큐.
  Pop → 페이지 가져옴 → 링크 추출 → 새 URL 들을 큐에 push.
  visited URL 셋으로 중복 차단.

운영 이슈:
  - 큐 크기 폭발 → priority queue 로 전환 (PageRank 가중치)
  - 같은 도메인 너무 많이 큐에 → 도메인별 rate limit / robots.txt
  - 무한 깊이 → max depth cutoff
  - 중복 URL → Bloom filter (메모리 절약, 약간의 false positive 허용)
  - 분산 → URL 해시 기반 partition

본질은 BFS. 단지 production 제약이 다 따라붙는다.
```

### 11.4 Kubernetes Pod Scheduling / Service Mesh 토폴로지

```
"가장 가까운 healthy pod 로 라우팅" = multi-source BFS.
  모든 healthy pod 를 출발점으로 BFS.
  client 가 어느 pod 와 가장 가까운지 한 번에 결정.

또는:
  Service mesh (Istio, Linkerd) 의 endpoint discovery
  Topology-aware routing: same-zone > same-region > cross-region 우선순위
  K-hop graph traversal 로 의존성 분석 (서비스 A 가 죽으면 어떤 서비스가 영향?)
```

### 11.5 Cascading Failure 분석 — "감염 확산" 모델

```
서비스 A 가 죽으면 B, C 가 영향. B, C 가 죽으면 D, E, F 가 영향...
이게 multi-source BFS 의 운영 매핑.

  큐 = 죽은 서비스 set
  edge = 의존성
  BFS = "K초 후 어디까지 장애가 퍼지는가?"

분석:
  - SPOF (Single Point of Failure) 찾기 — 노드 제거 시 그래프 분리
  - Blast radius — 한 서비스가 죽었을 때 K-hop 안의 서비스 수
  - Cycle detection — 순환 의존성 → 부팅 데드락 위험
```

### 11.6 GC Reachability — JVM 의 BFS

```
JVM 의 GC mark phase = BFS / DFS.
  GC root (스택, 스태틱, JNI) 부터 출발.
  reachable 객체를 마킹.

G1/CMS/ZGC 모두 reachability tracing 은 BFS-like.
운영:
  - heap 덤프 분석 (jhat, MAT) 도 BFS 로 retention path 추적.
  - "이 객체가 GC 안 되는 이유?" → BFS 로 GC root 까지 역추적.
  - Memory leak suspect = retention path 분석 (Eclipse MAT 의 핵심 기능).
```

### 11.7 Dependency Resolution — npm/maven/gradle

```
빌드 도구의 transitive dependency 해결 = BFS 또는 위상정렬.
  직접 의존성 → BFS 한 레벨.
  그 레벨의 의존성 → 다음 레벨.
  ...
  visited 셋으로 중복 차단.

운영:
  - "dependency hell" = BFS 결과에 같은 패키지 다른 버전 충돌.
  - Lock file = BFS 결과 스냅샷 (package-lock.json, Gemfile.lock).
  - 빌드 속도 = BFS 너비 × 네트워크 latency.
```

### 11.8 Database Index — B-tree 와의 비교

```
B+tree 검색은 BFS 가 아니라 깊이 = log_b N 의 단순 트리 walk.
하지만 LSM-tree 의 compaction 트리거, MongoDB sharded cluster 의 routing 은
BFS 로 토폴로지를 탐색.

특히 Sharding key 변경 시 "어떤 chunk가 어디로 이동해야 하는가" 를
shard graph 위의 BFS / matching 문제로 푼다.
```

---

## 12. 마스터 체크리스트 — 백지에서 확인

면접 직전 백지에 다음을 그릴 수 있는가?

- [ ] 큐 상태 변화 다이어그램 (시작 → 한 레벨 → 두 레벨)
- [ ] 큐의 불변식 `[d, ..., d, d+1, ...]` 그리고 왜 최단 거리가 보장되는지
- [ ] DFS vs BFS 비교표 (자료구조, 메모리, 최단 거리)
- [ ] visited 마킹 위치 (push 시점) 와 잘못된 위치 시 큐 폭발 시뮬레이션
- [ ] 4방향 / 8방향 / 나이트 이동의 dx/dy
- [ ] multi-source BFS 그림 (여러 출발점 동시 확산)
- [ ] 0-1 BFS deque 동작 (addFirst/addLast)
- [ ] 양방향 BFS 의 b^d → 2·b^(d/2) 분석
- [ ] 레벨 처리 패턴 — `int size = q.size()` 캡처 이유
- [ ] BFS → Dijkstra → Bellman-Ford 사다리
- [ ] Kahn's algorithm = in-degree 기반 BFS
- [ ] K-hop, traceroute, crawler, GC mark, dependency resolution 의 BFS 매핑

이걸 다 입으로 줄줄 풀면서 그릴 수 있으면 BFS 마스터.

---

## 13. 한 줄 요약

> **BFS = 가중치 없는 그래프의 최단 거리 보장 알고리즘.** 큐의 불변식 `[d, ..., d, d+1, ...]` 로 처음 도달이 곧 최단. visited 는 push 시점에 마킹. multi-source 로 N개의 출발점을 동시에 확산시켜 "각 점에서 가장 가까운 X" 를 O(V+E) 에 푼다. 0-1 BFS, 양방향 BFS, level 캡처는 BFS 의 세 가지 핵심 변주. 운영에서는 K-hop 추천, traceroute, crawler, K8s scheduling, cascading failure, GC mark, dependency resolution 이 모두 BFS 한 줄로 환원된다.
