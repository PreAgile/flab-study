# 11. Graph (그래프) — Union-Find · 위상정렬 · Dijkstra · Bellman-Ford · MST

> "그래프? BFS/DFS로 푸는 거"는 입문자. 시니어는 문제를 30초 안에 다음과 같이 분류한다.
>
> - "그룹/연결 컴포넌트?" → **Union-Find**
> - "선후 관계, prerequisite, build order?" → **위상 정렬 (Kahn / DFS)**
> - "single-source 최단경로, 모든 가중치 ≥ 0?" → **Dijkstra**
> - "음수 가중치 / 음수 사이클 검출?" → **Bellman-Ford / SPFA**
> - "모든 쌍 최단경로, V ≤ 400?" → **Floyd-Warshall**
> - "최소 비용으로 전부 연결?" → **MST (Kruskal / Prim)**
>
> 라이브 코딩에서 "그래프 문제다"라는 한 줄을 듣고 "어떤 알고리즘이 적합한가"를 즉답하지 못하면 그 문제는 시간 안에 못 푼다.
> 이 챕터는 옵션값 외우기가 아니라 **알고리즘이 가정하는 그래프 성질·왜 동작하는지·언제 깨지는지**를 정복하는 것이 목표다.

---

## 0. 인지 신호 (Trigger Signals)

문제 설명에서 다음 키워드가 보이면 즉시 분류한다.

| 키워드 / 상황 | 패턴 | 이유 |
|---|---|---|
| "친구의 친구", "같은 그룹", "connected components 개수" | **Union-Find** | 동적으로 그룹 merge·find. BFS/DFS 가능하지만 edge가 스트리밍이면 UF 압승 |
| "redundant edge", "cycle detection (무방향)" | **Union-Find** | 같은 root에 union 시도 = cycle |
| "prerequisite", "build order", "course schedule", "task dependency" | **Topological Sort** | DAG의 선후 순서. cycle 있으면 불가능 |
| "단일 출발점 → 모든 노드 최단", "weight ≥ 0", "지하철/도로/네트워크 지연" | **Dijkstra** | greedy + heap. O((V+E) log V) |
| "음수 가중치", "음수 사이클 검출", "환율 차익", "최대 K번 환승" | **Bellman-Ford** | 모든 edge를 V-1번 relax. SPFA는 큐 기반 최적화 |
| "모든 쌍의 최단거리", "V ≤ 400", "거리 행렬 출력" | **Floyd-Warshall** | O(V³). DP로 중간 노드 k를 하나씩 허용 |
| "최소 비용 케이블/도로 연결", "전체를 spanning", "MST" | **Kruskal / Prim** | greedy. cut property |
| "그래프가 dense (E ≈ V²)" | 인접 행렬 + Prim O(V²) | 메모리 V² 감당 가능할 때 |
| "그래프가 sparse (E ≈ V)" | 인접 리스트 + Kruskal | 정렬 O(E log E)가 유리 |

**역신호 (그래프가 아닐 가능성)**:

- "정렬된 배열에서 합" → Two Pointers
- "연속된 부분배열" → Sliding Window
- "트리만" (사이클 없음, 부모 명시) → Tree 패턴 (14장)
- "격자 위 이동" → Matrix 패턴 (16장). 단, BFS/DFS의 변형이므로 그래프 사고가 필요

---

## 1. 백지 그리기 (Whiteboard)

### 1.1 그래프 표현 3가지

```
예시 그래프:  1 ─ 2
              │   │
              3 ─ 4
edges: (1,2), (1,3), (2,4), (3,4)

[1] 인접 행렬 (Adjacency Matrix)
       1 2 3 4
    1  0 1 1 0
    2  1 0 0 1
    3  1 0 0 1
    4  0 1 1 0

   ✓ 두 노드 사이 edge 존재 확인 O(1)
   ✗ 메모리 O(V²) — V=10^5이면 80GB. 불가능.
   ✗ 인접 노드 순회 O(V) — sparse면 낭비
   → V ≤ 500 정도, dense graph일 때만

[2] 인접 리스트 (Adjacency List) — 가장 일반적
    1 → [2, 3]
    2 → [1, 4]
    3 → [1, 4]
    4 → [2, 3]

   ✓ 메모리 O(V + E)
   ✓ 인접 순회 O(deg(v))
   ✗ "(u,v) edge 있나?" 확인 O(deg(u))
   → 99%의 문제는 이거

[3] Edge List (간선 리스트)
    [(1,2), (1,3), (2,4), (3,4)]

   ✓ 가장 단순. Kruskal MST에 최적 (정렬해야 하므로)
   ✓ Bellman-Ford에도 적합 (모든 edge V-1번 순회)
   ✗ "v의 이웃" 같은 쿼리 불가
   → MST, Bellman-Ford 전용
```

**가중치/방향**: 인접 리스트는 `List<int[]>` (이웃, 가중치). 방향 그래프는 한 방향만, 무방향은 양쪽 다 추가.

### 1.2 Union-Find (Disjoint Set Union, DSU)

```
초기 상태 (각자 자기 자신이 root):

    [0]  [1]  [2]  [3]  [4]
parent: 0    1    2    3    4

union(0, 1):
    [1]              parent[0] = 1
    │
    [0]              "0의 root = 1"

union(2, 3):
    [3]              parent[2] = 3
    │
    [2]

union(1, 3):  rank 비교 → 같으면 한쪽을 다른쪽 밑으로
    [3]              parent[1] = 3
   / \
  [1] [2]
  │
  [0]

find(0):
    0 → 1 → 3 → 3   "root = 3"

Path Compression (최적화):
    find 중 만난 모든 노드를 root에 직접 연결
    [3]
   /|\
  0 1 2          ← 다음 find(0)는 O(1)
```

**Union by Rank**: tree 높이(rank)가 낮은 쪽을 높은 쪽 밑에 붙여서 트리 균형 유지. Path Compression과 함께 쓰면 amortized α(n) — practically O(1).

### 1.3 Kahn 위상정렬 (BFS 기반)

```
DAG:   1 → 2 → 4
       ↓   ↓
       3 → 5

indegree:  1:0  2:1  3:1  4:1  5:2

Step 1: indegree=0인 노드 큐에 → [1]
Step 2: 1 pop, 출력 [1]. 이웃(2,3)의 indegree--
        indegree:  2:0  3:0  4:1  5:2
        큐: [2, 3]
Step 3: 2 pop, 출력 [1,2]. 이웃(4,5) indegree--
        indegree:  3:0  4:0  5:1
        큐: [3, 4]
Step 4: 3 pop, 출력 [1,2,3]. 이웃(5) indegree--
        indegree:  4:0  5:0
        큐: [4, 5]
Step 5,6: 4, 5 차례로 pop
        결과: [1, 2, 3, 4, 5]

✓ 출력 노드 수 < V → 사이클 존재
```

### 1.4 Dijkstra (PriorityQueue)

```
가중치 그래프 (출발: 1):
       2
   1 ─────▶ 2
   │ 5      │ 1
   ▼        ▼
   3 ─────▶ 4
       3

dist[]: 1:0  2:∞  3:∞  4:∞
heap:   [(0, 1)]

Pop (0, 1):
   relax 1→2 (2):  dist[2] = 0+2 = 2, push (2, 2)
   relax 1→3 (5):  dist[3] = 0+5 = 5, push (5, 3)
   heap: [(2,2), (5,3)]

Pop (2, 2):
   relax 2→4 (1):  dist[4] = 2+1 = 3, push (3, 4)
   heap: [(3,4), (5,3)]

Pop (3, 4):  (4는 도착, 인접 없음)
   heap: [(5,3)]

Pop (5, 3):
   relax 3→4 (3):  dist[4]=3 < 5+3=8, skip
   heap: []

최종 dist: 1:0  2:2  3:5  4:3
```

**핵심**: heap에서 pop된 노드는 "이미 확정된 최단거리". 다시 처리 안 함.
**음수 가중치에서 깨지는 이유**: 한 번 확정된 dist가 나중에 음수 edge로 더 작아질 수 있음. Greedy 가정 위반.

### 1.5 Bellman-Ford (Relaxation)

```
모든 edge를 V-1번 반복 relax.

for i in 1..V-1:
    for (u, v, w) in edges:
        if dist[u] + w < dist[v]:
            dist[v] = dist[u] + w

추가 1회 더 돌려서 값이 갱신되면 → 음수 사이클 존재.

직관:
- 최단경로의 edge 개수 ≤ V-1 (사이클이 없으므로)
- 1회 iteration 후: 최소 1 edge짜리 경로 완성
- k회 iteration 후: 최소 k edge짜리 경로 완성
- V-1회면 모든 경로 커버
```

### 1.6 MST — Kruskal vs Prim

```
Kruskal (Edge 기반, Union-Find):
1. 모든 edge를 가중치 오름차순 정렬
2. 작은 것부터 선택, 사이클 안 만들면 union
3. V-1개 edge가 선택되면 끝

   edges 정렬: (1,2,1), (3,4,2), (1,3,3), (2,4,4), (1,4,5)
   pick (1,2,1): union(1,2)  ✓
   pick (3,4,2): union(3,4)  ✓
   pick (1,3,3): union(1,3)  ✓ (지금까지 3 edges = V-1)
   끝.  cost = 1+2+3 = 6


Prim (Node 기반, PriorityQueue):
1. 임의 시작 노드를 MST에 포함
2. MST와 외부를 잇는 edge 중 최소를 선택 → 노드 추가
3. 모든 노드 추가될 때까지 반복

   start=1, heap=[(1,2),(3,3),(5,4)] (1에서 나가는 edges)
   pick (1,2): add 2, heap += (4,4)
   pick (3,3): add 3, heap += (2,4) ← 갱신
   pick (2,4): add 4
   cost = 1+3+2 = 6
```

**Kruskal**: sparse graph (E 작음) — 정렬이 빠르다.
**Prim**: dense graph (E ≈ V²) — heap pop이 V번이라 유리.

---

## 2. 직관과 정의 — 각 알고리즘의 가정

| 알고리즘 | 그래프 가정 | 핵심 아이디어 | 깨지면 |
|---|---|---|---|
| **Union-Find** | 무방향, 동적 union | 트리로 그룹 표현 + path compression | 방향 그래프엔 부적합 |
| **Topological Sort** | **DAG (사이클 없는 방향)** | indegree 0부터 제거 | 사이클 → 순서 불가능 |
| **Dijkstra** | **가중치 ≥ 0** | 가장 가까운 노드부터 확정 (greedy) | 음수 edge → 잘못된 답 |
| **Bellman-Ford** | 음수 OK, 음수 사이클 검출 | V-1번 relax | 음수 사이클 → 최단경로 정의 불가 |
| **Floyd-Warshall** | 음수 OK (사이클 X), 모든 쌍 | 중간 노드 k를 하나씩 허용 | V ≥ 500이면 O(V³) 터짐 |
| **MST (Kruskal/Prim)** | **무방향, 연결 그래프** | Cut property: 최소 edge가 항상 MST에 포함 | 방향이면 Edmonds' algorithm 필요 |

### 2.1 왜 Dijkstra는 음수에서 깨지나?

```
A ──(1)──▶ B
│          │
(2)      (-3)
│          │
▼          ▼
C  ◀──────┘  C로 가는 음수 edge

Dijkstra:  A→C dist=2 확정.
           B 처리 시 B→C로 1+(-3)=-2 발견했지만 C는 이미 "확정"이라 update 안 함.
           → 잘못된 답.
```

Dijkstra의 greedy invariant: "heap에서 pop된 dist는 이미 최종"이라는 가정. 음수가 있으면 나중에 더 작아질 수 있어서 invariant가 깨진다.

### 2.2 왜 Bellman-Ford는 V-1번이면 충분한가?

최단 경로는 사이클을 포함하지 않는다 (양수 사이클은 빼는 게 이득, 음수 사이클은 무한히 줄어서 정의 불가). 따라서 경로 길이 ≤ V-1 edge. k번째 iteration 후 "edge k개 이하 경로의 최단값"이 보장된다 (induction).

### 2.3 왜 위상정렬은 DAG에서만 가능한가?

사이클 A → B → A가 있으면 "A보다 B 먼저"와 "B보다 A 먼저"가 모순. Kahn에서는 indegree 0인 노드가 다 떨어진 뒤에도 남은 노드가 있으면 사이클.

---

## 3. Java 템플릿

### 3.1 그래프 표현 (인접 리스트)

```java
import java.util.*;

// 무가중치
List<List<Integer>> graph = new ArrayList<>();
for (int i = 0; i <= n; i++) graph.add(new ArrayList<>());
for (int[] e : edges) {
    graph.get(e[0]).add(e[1]);
    graph.get(e[1]).add(e[0]);  // 무방향이면 양쪽
}

// 가중치
List<List<int[]>> wgraph = new ArrayList<>();
for (int i = 0; i <= n; i++) wgraph.add(new ArrayList<>());
for (int[] e : edges) {
    wgraph.get(e[0]).add(new int[]{e[1], e[2]});  // [to, weight]
}
```

### 3.2 Union-Find (Path Compression + Union by Rank)

```java
class UnionFind {
    int[] parent, rank;
    int components;

    UnionFind(int n) {
        parent = new int[n];
        rank = new int[n];
        components = n;
        for (int i = 0; i < n; i++) parent[i] = i;
    }

    int find(int x) {
        if (parent[x] != x) {
            parent[x] = find(parent[x]);  // path compression
        }
        return parent[x];
    }

    boolean union(int a, int b) {
        int ra = find(a), rb = find(b);
        if (ra == rb) return false;  // 이미 같은 그룹 (cycle)
        // union by rank
        if (rank[ra] < rank[rb]) { parent[ra] = rb; }
        else if (rank[ra] > rank[rb]) { parent[rb] = ra; }
        else { parent[rb] = ra; rank[ra]++; }
        components--;
        return true;
    }

    boolean connected(int a, int b) {
        return find(a) == find(b);
    }
}
```

**stack overflow 주의**: find 재귀가 깊어질 수 있다 (n=10^6 트리). 이론적으로는 path compression으로 평탄해지지만, **첫 호출 전엔 깊을 수 있다**. 안전하게 iterative로:

```java
int find(int x) {
    int root = x;
    while (parent[root] != root) root = parent[root];
    while (parent[x] != root) {
        int next = parent[x];
        parent[x] = root;
        x = next;
    }
    return root;
}
```

### 3.3 위상정렬 (Kahn, BFS 기반)

```java
int[] topologicalSort(int n, int[][] prerequisites) {
    List<List<Integer>> graph = new ArrayList<>();
    int[] indegree = new int[n];
    for (int i = 0; i < n; i++) graph.add(new ArrayList<>());
    for (int[] p : prerequisites) {
        // p[1] -> p[0] (p[1]을 먼저 해야 p[0] 가능)
        graph.get(p[1]).add(p[0]);
        indegree[p[0]]++;
    }

    Deque<Integer> queue = new ArrayDeque<>();
    for (int i = 0; i < n; i++) if (indegree[i] == 0) queue.offer(i);

    int[] order = new int[n];
    int idx = 0;
    while (!queue.isEmpty()) {
        int u = queue.poll();
        order[idx++] = u;
        for (int v : graph.get(u)) {
            if (--indegree[v] == 0) queue.offer(v);
        }
    }
    return idx == n ? order : new int[0];  // 사이클이면 빈 배열
}
```

### 3.4 Dijkstra (PriorityQueue, O((V+E) log V))

```java
int[] dijkstra(int n, List<List<int[]>> graph, int start) {
    int[] dist = new int[n];
    Arrays.fill(dist, Integer.MAX_VALUE);
    dist[start] = 0;

    // [거리, 노드], 거리 오름차순
    PriorityQueue<int[]> pq = new PriorityQueue<>((a, b) -> a[0] - b[0]);
    pq.offer(new int[]{0, start});

    while (!pq.isEmpty()) {
        int[] cur = pq.poll();
        int d = cur[0], u = cur[1];
        if (d > dist[u]) continue;  // stale entry skip — 핵심

        for (int[] nb : graph.get(u)) {
            int v = nb[0], w = nb[1];
            if (dist[u] + w < dist[v]) {
                dist[v] = dist[u] + w;
                pq.offer(new int[]{dist[v], v});
            }
        }
    }
    return dist;
}
```

**stale entry skip**: heap에 같은 노드의 옛 거리가 여러 번 들어갈 수 있다 (decrease-key 대신 push). pop 시 dist[u]보다 크면 무시. 이게 없으면 시간 폭증.

**오버플로우 주의**: 가중치 합이 int 범위를 넘으면 Long 써야 함.

### 3.5 Bellman-Ford (O(VE))

```java
long[] bellmanFord(int n, int[][] edges, int start) {
    long[] dist = new long[n];
    Arrays.fill(dist, Long.MAX_VALUE);
    dist[start] = 0;

    for (int i = 0; i < n - 1; i++) {
        boolean updated = false;
        for (int[] e : edges) {
            int u = e[0], v = e[1], w = e[2];
            if (dist[u] != Long.MAX_VALUE && dist[u] + w < dist[v]) {
                dist[v] = dist[u] + w;
                updated = true;
            }
        }
        if (!updated) break;  // 조기 종료
    }

    // 음수 사이클 검출: 한 번 더 돌려서 갱신되면 음수 사이클
    for (int[] e : edges) {
        int u = e[0], v = e[1], w = e[2];
        if (dist[u] != Long.MAX_VALUE && dist[u] + w < dist[v]) {
            return null;  // negative cycle
        }
    }
    return dist;
}
```

### 3.6 Floyd-Warshall (O(V³))

```java
long[][] floydWarshall(int n, int[][] edges) {
    long[][] dist = new long[n][n];
    for (long[] row : dist) Arrays.fill(row, Long.MAX_VALUE / 4);
    for (int i = 0; i < n; i++) dist[i][i] = 0;
    for (int[] e : edges) dist[e[0]][e[1]] = Math.min(dist[e[0]][e[1]], e[2]);

    for (int k = 0; k < n; k++) {                 // 중간 노드
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < n; j++) {
                if (dist[i][k] + dist[k][j] < dist[i][j]) {
                    dist[i][j] = dist[i][k] + dist[k][j];
                }
            }
        }
    }
    return dist;
}
```

`MAX_VALUE / 4`: overflow 방지. 두 거리 더할 때 overflow 안 나도록 충분히 큰 값.

### 3.7 Kruskal (MST, Union-Find 사용)

```java
long kruskal(int n, int[][] edges) {
    Arrays.sort(edges, (a, b) -> a[2] - b[2]);
    UnionFind uf = new UnionFind(n);
    long total = 0;
    int picked = 0;
    for (int[] e : edges) {
        if (uf.union(e[0], e[1])) {
            total += e[2];
            if (++picked == n - 1) break;
        }
    }
    return picked == n - 1 ? total : -1;  // 연결 불가
}
```

### 3.8 Prim (MST, PriorityQueue)

```java
long prim(int n, List<List<int[]>> graph) {
    boolean[] inMst = new boolean[n];
    PriorityQueue<int[]> pq = new PriorityQueue<>((a, b) -> a[0] - b[0]);
    pq.offer(new int[]{0, 0});  // [weight, node]
    long total = 0;
    int count = 0;

    while (!pq.isEmpty() && count < n) {
        int[] cur = pq.poll();
        int w = cur[0], u = cur[1];
        if (inMst[u]) continue;
        inMst[u] = true;
        total += w;
        count++;
        for (int[] nb : graph.get(u)) {
            if (!inMst[nb[0]]) pq.offer(new int[]{nb[1], nb[0]});
        }
    }
    return count == n ? total : -1;
}
```

---

## 4. Kotlin 템플릿

### 4.1 Union-Find

```kotlin
class UnionFind(n: Int) {
    private val parent = IntArray(n) { it }
    private val rank = IntArray(n)
    var components = n
        private set

    fun find(x: Int): Int {
        var root = x
        while (parent[root] != root) root = parent[root]
        var cur = x
        while (parent[cur] != root) {
            val next = parent[cur]
            parent[cur] = root
            cur = next
        }
        return root
    }

    fun union(a: Int, b: Int): Boolean {
        val ra = find(a); val rb = find(b)
        if (ra == rb) return false
        when {
            rank[ra] < rank[rb] -> parent[ra] = rb
            rank[ra] > rank[rb] -> parent[rb] = ra
            else -> { parent[rb] = ra; rank[ra]++ }
        }
        components--
        return true
    }

    fun connected(a: Int, b: Int) = find(a) == find(b)
}
```

### 4.2 위상정렬 (Kahn)

```kotlin
fun topologicalSort(n: Int, prerequisites: Array<IntArray>): IntArray {
    val graph = Array(n) { mutableListOf<Int>() }
    val indegree = IntArray(n)
    for (p in prerequisites) {
        graph[p[1]].add(p[0])
        indegree[p[0]]++
    }
    val queue: ArrayDeque<Int> = ArrayDeque()
    for (i in 0 until n) if (indegree[i] == 0) queue.addLast(i)

    val order = IntArray(n)
    var idx = 0
    while (queue.isNotEmpty()) {
        val u = queue.removeFirst()
        order[idx++] = u
        for (v in graph[u]) {
            if (--indegree[v] == 0) queue.addLast(v)
        }
    }
    return if (idx == n) order else IntArray(0)
}
```

### 4.3 Dijkstra

```kotlin
import java.util.PriorityQueue

fun dijkstra(n: Int, graph: List<List<IntArray>>, start: Int): IntArray {
    val dist = IntArray(n) { Int.MAX_VALUE }
    dist[start] = 0
    val pq = PriorityQueue<IntArray>(compareBy { it[0] })
    pq.offer(intArrayOf(0, start))

    while (pq.isNotEmpty()) {
        val (d, u) = pq.poll()
        if (d > dist[u]) continue
        for (nb in graph[u]) {
            val v = nb[0]; val w = nb[1]
            if (dist[u] + w < dist[v]) {
                dist[v] = dist[u] + w
                pq.offer(intArrayOf(dist[v], v))
            }
        }
    }
    return dist
}
```

### 4.4 Bellman-Ford

```kotlin
fun bellmanFord(n: Int, edges: Array<IntArray>, start: Int): LongArray? {
    val dist = LongArray(n) { Long.MAX_VALUE }
    dist[start] = 0L
    for (i in 0 until n - 1) {
        var updated = false
        for (e in edges) {
            val u = e[0]; val v = e[1]; val w = e[2]
            if (dist[u] != Long.MAX_VALUE && dist[u] + w < dist[v]) {
                dist[v] = dist[u] + w
                updated = true
            }
        }
        if (!updated) break
    }
    for (e in edges) {
        val u = e[0]; val v = e[1]; val w = e[2]
        if (dist[u] != Long.MAX_VALUE && dist[u] + w < dist[v]) return null
    }
    return dist
}
```

### 4.5 Kruskal MST

```kotlin
fun kruskal(n: Int, edges: Array<IntArray>): Long {
    edges.sortBy { it[2] }
    val uf = UnionFind(n)
    var total = 0L
    var picked = 0
    for (e in edges) {
        if (uf.union(e[0], e[1])) {
            total += e[2]
            if (++picked == n - 1) break
        }
    }
    return if (picked == n - 1) total else -1L
}
```

---

## 5. 시간/공간 복잡도

| 알고리즘 | 시간 | 공간 | 비고 |
|---|---|---|---|
| **Union-Find** | amortized **α(n)** per op | O(N) | α(n) ≤ 4 for n ≤ 2^65536 → 사실상 O(1) |
| **BFS/DFS** | O(V + E) | O(V) | 인접 리스트 기준 |
| **Topological Sort (Kahn)** | O(V + E) | O(V + E) | indegree 배열 + 큐 |
| **Dijkstra (heap)** | O((V + E) log V) | O(V + E) | 음수 가중치 X |
| **Dijkstra (배열)** | O(V²) | O(V²) | dense graph에 유리 |
| **Bellman-Ford** | O(V × E) | O(V) | 음수 OK, 음수 사이클 검출 가능 |
| **SPFA** | 평균 O(kE), 최악 O(VE) | O(V) | Bellman-Ford 큐 최적화 |
| **Floyd-Warshall** | O(V³) | O(V²) | V ≤ 400~500 |
| **Kruskal (MST)** | O(E log E) | O(V) | 정렬 + UF |
| **Prim (heap)** | O((V + E) log V) | O(V + E) | dense엔 Prim O(V²) |

**α(n) 의미**: Inverse Ackermann function. 우주의 모든 입자 수보다 큰 n에 대해서도 α(n) ≤ 4. 그래서 "사실상 O(1)"이라 부른다. 단, **단일 op은 최악 O(log n)일 수 있다** (rank 없는 union 시) — P99 latency 분석엔 주의.

**Dijkstra의 log V**: heap에 최대 E개의 entry. 각 pop/push가 O(log E) = O(log V²) = O(log V).

**Bellman-Ford O(VE)**: V=10^4, E=10^5이면 10^9 → TLE. Bellman-Ford는 음수가 정말 필요할 때만.

---

## 6. 대표 문제

### 6.1 LeetCode 207 — Course Schedule

> n개의 코스, prerequisites[i] = [a, b]는 "a를 들으려면 b를 먼저". 모든 코스 가능?

**접근**: DAG에서 위상정렬 가능 ↔ 사이클 없음 ↔ 가능. Kahn으로 출력 노드 수 < n이면 사이클.

**Java**:

```java
public boolean canFinish(int n, int[][] pre) {
    List<List<Integer>> g = new ArrayList<>();
    int[] in = new int[n];
    for (int i = 0; i < n; i++) g.add(new ArrayList<>());
    for (int[] p : pre) {
        g.get(p[1]).add(p[0]);
        in[p[0]]++;
    }
    Deque<Integer> q = new ArrayDeque<>();
    for (int i = 0; i < n; i++) if (in[i] == 0) q.offer(i);
    int done = 0;
    while (!q.isEmpty()) {
        int u = q.poll();
        done++;
        for (int v : g.get(u)) if (--in[v] == 0) q.offer(v);
    }
    return done == n;
}
```

**Kotlin**:

```kotlin
fun canFinish(n: Int, pre: Array<IntArray>): Boolean {
    val g = Array(n) { mutableListOf<Int>() }
    val indeg = IntArray(n)
    for (p in pre) { g[p[1]].add(p[0]); indeg[p[0]]++ }
    val q: ArrayDeque<Int> = ArrayDeque()
    for (i in 0 until n) if (indeg[i] == 0) q.addLast(i)
    var done = 0
    while (q.isNotEmpty()) {
        val u = q.removeFirst()
        done++
        for (v in g[u]) if (--indeg[v] == 0) q.addLast(v)
    }
    return done == n
}
```

**복잡도**: O(V + E).
**함정**:
- `[1, 0]`이 "1을 들으려면 0 먼저"인지 "0이 1의 prerequisite"인지 문제마다 헷갈림. 화살표 방향을 칠판에 그리고 시작.
- 자기 자신 prerequisite (a, a) → indegree 1로 시작, 영원히 0 안 됨, 사이클로 정확히 검출됨.

---

### 6.2 LeetCode 210 — Course Schedule II

> 207과 같지만 가능한 순서를 출력.

**접근**: Kahn 위상정렬 결과 그대로 반환. 사이클이면 빈 배열.

**Java**:

```java
public int[] findOrder(int n, int[][] pre) {
    List<List<Integer>> g = new ArrayList<>();
    int[] in = new int[n];
    for (int i = 0; i < n; i++) g.add(new ArrayList<>());
    for (int[] p : pre) { g.get(p[1]).add(p[0]); in[p[0]]++; }
    Deque<Integer> q = new ArrayDeque<>();
    for (int i = 0; i < n; i++) if (in[i] == 0) q.offer(i);
    int[] order = new int[n];
    int idx = 0;
    while (!q.isEmpty()) {
        int u = q.poll();
        order[idx++] = u;
        for (int v : g.get(u)) if (--in[v] == 0) q.offer(v);
    }
    return idx == n ? order : new int[0];
}
```

**Kotlin**: 위 4.2 템플릿 그대로.

**복잡도**: O(V + E).
**함정**: 여러 valid 순서가 있을 수 있음. 문제 채점은 보통 어느 순서든 OK.

---

### 6.3 LeetCode 547 — Number of Provinces

> n×n isConnected 행렬. isConnected[i][j]=1이면 i와 j 직접 친구. "province" (연결 컴포넌트) 개수?

**접근**: Union-Find로 모든 (i,j) 쌍 union, 마지막에 distinct root 개수.
대안: DFS로 component 세기.

**Java (UF)**:

```java
public int findCircleNum(int[][] m) {
    int n = m.length;
    UnionFind uf = new UnionFind(n);
    for (int i = 0; i < n; i++) {
        for (int j = i + 1; j < n; j++) {  // 대칭이므로 상삼각만
            if (m[i][j] == 1) uf.union(i, j);
        }
    }
    return uf.components;
}
```

**Kotlin**:

```kotlin
fun findCircleNum(m: Array<IntArray>): Int {
    val n = m.size
    val uf = UnionFind(n)
    for (i in 0 until n) {
        for (j in i + 1 until n) {
            if (m[i][j] == 1) uf.union(i, j)
        }
    }
    return uf.components
}
```

**복잡도**: O(n² × α(n)).
**함정**:
- m[i][i] = 1 (자기 자신) → 같은 그룹 union (no-op, false 반환).
- 대칭 행렬 가정 — 상삼각만 봐도 OK.

---

### 6.4 LeetCode 684 — Redundant Connection

> 트리(n노드 n-1 edge)에 edge 하나 추가됨 (총 n edge). 제거하면 다시 트리가 되는 edge 반환 (마지막에 등장한 것).

**접근**: edge를 순서대로 union 하면서, 이미 같은 그룹이면 그 edge가 redundant. UF의 정수.

**Java**:

```java
public int[] findRedundantConnection(int[][] edges) {
    int n = edges.length;
    UnionFind uf = new UnionFind(n + 1);  // 1-indexed
    for (int[] e : edges) {
        if (!uf.union(e[0], e[1])) return e;
    }
    return new int[0];
}
```

**Kotlin**:

```kotlin
fun findRedundantConnection(edges: Array<IntArray>): IntArray {
    val uf = UnionFind(edges.size + 1)
    for (e in edges) {
        if (!uf.union(e[0], e[1])) return e
    }
    return intArrayOf()
}
```

**복잡도**: O(N × α(N)).
**함정**: 1-indexed. UF 크기를 n+1로 잡지 않으면 ArrayIndexOutOfBounds.

---

### 6.5 LeetCode 743 — Network Delay Time (Dijkstra)

> n개 노드, times[i] = [u, v, w] 방향 가중치 edge. 노드 k에서 신호 전파 시 모든 노드가 받는 데 걸리는 최소 시간 (불가능하면 -1).

**접근**: k에서 Dijkstra. dist의 최댓값이 답. MAX_VALUE 남아있으면 -1.

**Java**:

```java
public int networkDelayTime(int[][] times, int n, int k) {
    List<List<int[]>> g = new ArrayList<>();
    for (int i = 0; i <= n; i++) g.add(new ArrayList<>());
    for (int[] t : times) g.get(t[0]).add(new int[]{t[1], t[2]});

    int[] dist = new int[n + 1];
    Arrays.fill(dist, Integer.MAX_VALUE);
    dist[k] = 0;
    PriorityQueue<int[]> pq = new PriorityQueue<>((a, b) -> a[0] - b[0]);
    pq.offer(new int[]{0, k});

    while (!pq.isEmpty()) {
        int[] cur = pq.poll();
        int d = cur[0], u = cur[1];
        if (d > dist[u]) continue;
        for (int[] nb : g.get(u)) {
            int v = nb[0], w = nb[1];
            if (d + w < dist[v]) {
                dist[v] = d + w;
                pq.offer(new int[]{dist[v], v});
            }
        }
    }
    int ans = 0;
    for (int i = 1; i <= n; i++) {
        if (dist[i] == Integer.MAX_VALUE) return -1;
        ans = Math.max(ans, dist[i]);
    }
    return ans;
}
```

**Kotlin**:

```kotlin
fun networkDelayTime(times: Array<IntArray>, n: Int, k: Int): Int {
    val g = Array(n + 1) { mutableListOf<IntArray>() }
    for (t in times) g[t[0]].add(intArrayOf(t[1], t[2]))
    val dist = IntArray(n + 1) { Int.MAX_VALUE }
    dist[k] = 0
    val pq = PriorityQueue<IntArray>(compareBy { it[0] })
    pq.offer(intArrayOf(0, k))
    while (pq.isNotEmpty()) {
        val (d, u) = pq.poll()
        if (d > dist[u]) continue
        for (nb in g[u]) {
            val v = nb[0]; val w = nb[1]
            if (d + w < dist[v]) {
                dist[v] = d + w
                pq.offer(intArrayOf(dist[v], v))
            }
        }
    }
    var ans = 0
    for (i in 1..n) {
        if (dist[i] == Int.MAX_VALUE) return -1
        ans = maxOf(ans, dist[i])
    }
    return ans
}
```

**복잡도**: O((V + E) log V).
**함정**:
- 1-indexed. 배열 크기 n+1.
- 모든 가중치 ≥ 0 보장 (문제 조건). Dijkstra OK.
- stale entry skip 빼면 TLE.

---

### 6.6 LeetCode 787 — Cheapest Flights Within K Stops (Bellman-Ford)

> n 도시, flights[i]=[u,v,w] 방향 가중치. src→dst까지 최대 K stop으로 갈 수 있는 최소 비용. 불가능이면 -1.

**접근**: 일반 Dijkstra는 "stop 제한"을 직접 다루기 어려움. Bellman-Ford를 K+1번만 돌리면 "edge 수 ≤ K+1인 경로"가 자연스럽게 나옴.
**핵심**: 각 iteration에서 직전 iteration의 dist를 snapshot하고 그것만 보고 relax (아니면 한 iteration 안에서 chain됨).

**Java**:

```java
public int findCheapestPrice(int n, int[][] flights, int src, int dst, int K) {
    int INF = Integer.MAX_VALUE / 2;
    int[] dist = new int[n];
    Arrays.fill(dist, INF);
    dist[src] = 0;

    for (int i = 0; i <= K; i++) {
        int[] snapshot = dist.clone();   // 직전 라운드 값
        for (int[] f : flights) {
            int u = f[0], v = f[1], w = f[2];
            if (snapshot[u] + w < dist[v]) {
                dist[v] = snapshot[u] + w;
            }
        }
    }
    return dist[dst] >= INF ? -1 : dist[dst];
}
```

**Kotlin**:

```kotlin
fun findCheapestPrice(n: Int, flights: Array<IntArray>, src: Int, dst: Int, K: Int): Int {
    val INF = Int.MAX_VALUE / 2
    var dist = IntArray(n) { INF }
    dist[src] = 0
    for (i in 0..K) {
        val snapshot = dist.copyOf()
        for (f in flights) {
            val u = f[0]; val v = f[1]; val w = f[2]
            if (snapshot[u] + w < dist[v]) {
                dist[v] = snapshot[u] + w
            }
        }
    }
    return if (dist[dst] >= INF) -1 else dist[dst]
}
```

**복잡도**: O(K × E).
**함정**:
- `snapshot` 없이 그냥 dist를 in-place 갱신하면 한 iteration 안에서 2 edge 이상을 한 번에 쓰게 됨 → "stop K개" 의미 깨짐. **이걸 못 잡으면 면접에서 무조건 떨어진다.**
- K stop = K+1 edge. K=0이면 직항만.
- `Integer.MAX_VALUE / 2` 사용: 더해도 overflow 안 나도록.

---

### 6.7 LeetCode 1971 — Find if Path Exists in Graph

> n노드 무방향 그래프, source→destination 경로 존재?

**접근**: BFS/DFS도 가능. Union-Find가 가장 깔끔 — 모든 edge union 후 same root?

**Java (UF)**:

```java
public boolean validPath(int n, int[][] edges, int source, int destination) {
    UnionFind uf = new UnionFind(n);
    for (int[] e : edges) uf.union(e[0], e[1]);
    return uf.connected(source, destination);
}
```

**Kotlin**:

```kotlin
fun validPath(n: Int, edges: Array<IntArray>, source: Int, destination: Int): Boolean {
    val uf = UnionFind(n)
    for (e in edges) uf.union(e[0], e[1])
    return uf.connected(source, destination)
}
```

**복잡도**: O((N + E) × α(N)).
**함정**:
- source == destination이면 즉시 true.
- 무방향 (양쪽 union이 자동).
- 만약 query가 여러 개라면 UF가 BFS보다 훨씬 유리 (한 번 build 후 O(α) per query).

---

### 6.8 프로그래머스 — 가장 먼 노드 (BFS)

> n노드, edges (양방향). 1번 노드에서 가장 먼 노드 개수.

**접근**: 무가중치 → BFS. 1에서의 거리 = level. 최대 level 노드 수 카운트.

**Java**:

```java
class Solution {
    public int solution(int n, int[][] edge) {
        List<List<Integer>> g = new ArrayList<>();
        for (int i = 0; i <= n; i++) g.add(new ArrayList<>());
        for (int[] e : edge) {
            g.get(e[0]).add(e[1]);
            g.get(e[1]).add(e[0]);
        }
        int[] dist = new int[n + 1];
        Arrays.fill(dist, -1);
        dist[1] = 0;
        Deque<Integer> q = new ArrayDeque<>();
        q.offer(1);
        int maxDist = 0;
        while (!q.isEmpty()) {
            int u = q.poll();
            for (int v : g.get(u)) {
                if (dist[v] == -1) {
                    dist[v] = dist[u] + 1;
                    maxDist = Math.max(maxDist, dist[v]);
                    q.offer(v);
                }
            }
        }
        int count = 0;
        for (int i = 1; i <= n; i++) if (dist[i] == maxDist) count++;
        return count;
    }
}
```

**Kotlin**:

```kotlin
class Solution {
    fun solution(n: Int, edge: Array<IntArray>): Int {
        val g = Array(n + 1) { mutableListOf<Int>() }
        for (e in edge) { g[e[0]].add(e[1]); g[e[1]].add(e[0]) }
        val dist = IntArray(n + 1) { -1 }
        dist[1] = 0
        val q: ArrayDeque<Int> = ArrayDeque()
        q.addLast(1)
        var maxDist = 0
        while (q.isNotEmpty()) {
            val u = q.removeFirst()
            for (v in g[u]) if (dist[v] == -1) {
                dist[v] = dist[u] + 1
                maxDist = maxOf(maxDist, dist[v])
                q.addLast(v)
            }
        }
        return (1..n).count { dist[it] == maxDist }
    }
}
```

**복잡도**: O(V + E).
**함정**: 가중치 없으니 Dijkstra 쓰면 오버킬 (그래도 답은 맞음). BFS로 충분.

---

### 6.9 프로그래머스 — 순위 (Floyd-Warshall)

> n명, results[i] = [A, B] (A가 B를 이김). 정확히 순위가 결정되는 사람 수.

**접근**: 한 사람의 순위가 결정되려면 그를 기준으로 모든 사람과의 승패 관계가 직간접적으로 알려져 있어야 함 = 자신을 거치거나 자신에게 도달하는 사람 수가 n-1. Floyd-Warshall로 reachability 행렬 만들면 끝.

**Java**:

```java
class Solution {
    public int solution(int n, int[][] results) {
        boolean[][] win = new boolean[n + 1][n + 1];
        for (int[] r : results) win[r[0]][r[1]] = true;
        for (int k = 1; k <= n; k++) {
            for (int i = 1; i <= n; i++) {
                for (int j = 1; j <= n; j++) {
                    if (win[i][k] && win[k][j]) win[i][j] = true;
                }
            }
        }
        int answer = 0;
        for (int i = 1; i <= n; i++) {
            int known = 0;
            for (int j = 1; j <= n; j++) {
                if (i != j && (win[i][j] || win[j][i])) known++;
            }
            if (known == n - 1) answer++;
        }
        return answer;
    }
}
```

**Kotlin**:

```kotlin
class Solution {
    fun solution(n: Int, results: Array<IntArray>): Int {
        val win = Array(n + 1) { BooleanArray(n + 1) }
        for (r in results) win[r[0]][r[1]] = true
        for (k in 1..n) for (i in 1..n) for (j in 1..n) {
            if (win[i][k] && win[k][j]) win[i][j] = true
        }
        var answer = 0
        for (i in 1..n) {
            var known = 0
            for (j in 1..n) if (i != j && (win[i][j] || win[j][i])) known++
            if (known == n - 1) answer++
        }
        return answer
    }
}
```

**복잡도**: O(n³). n ≤ 100이라 OK.
**함정**:
- "순위가 결정된다" = "본인을 제외한 모든 사람과의 우열이 결정된다".
- 양방향이 아니라 단방향 (A→B 승). Floyd는 reachability에만 사용.

---

### 6.10 프로그래머스 — 섬 연결하기 (MST)

> n개 섬, costs[i] = [A, B, w]. 모두 연결하는 최소 비용.

**접근**: Kruskal MST 그대로.

**Java**:

```java
class Solution {
    int[] parent, rank_;
    int find(int x) {
        while (parent[x] != x) { parent[x] = parent[parent[x]]; x = parent[x]; }
        return x;
    }
    boolean union(int a, int b) {
        int ra = find(a), rb = find(b);
        if (ra == rb) return false;
        if (rank_[ra] < rank_[rb]) parent[ra] = rb;
        else if (rank_[ra] > rank_[rb]) parent[rb] = ra;
        else { parent[rb] = ra; rank_[ra]++; }
        return true;
    }
    public int solution(int n, int[][] costs) {
        Arrays.sort(costs, (a, b) -> a[2] - b[2]);
        parent = new int[n];
        rank_ = new int[n];
        for (int i = 0; i < n; i++) parent[i] = i;
        int total = 0, picked = 0;
        for (int[] c : costs) {
            if (union(c[0], c[1])) {
                total += c[2];
                if (++picked == n - 1) break;
            }
        }
        return total;
    }
}
```

**Kotlin**:

```kotlin
class Solution {
    lateinit var parent: IntArray
    lateinit var rank_: IntArray
    fun find(x: Int): Int {
        var c = x
        while (parent[c] != c) { parent[c] = parent[parent[c]]; c = parent[c] }
        return c
    }
    fun union(a: Int, b: Int): Boolean {
        val ra = find(a); val rb = find(b)
        if (ra == rb) return false
        when {
            rank_[ra] < rank_[rb] -> parent[ra] = rb
            rank_[ra] > rank_[rb] -> parent[rb] = ra
            else -> { parent[rb] = ra; rank_[ra]++ }
        }
        return true
    }
    fun solution(n: Int, costs: Array<IntArray>): Int {
        costs.sortBy { it[2] }
        parent = IntArray(n) { it }
        rank_ = IntArray(n)
        var total = 0; var picked = 0
        for (c in costs) {
            if (union(c[0], c[1])) {
                total += c[2]
                if (++picked == n - 1) break
            }
        }
        return total
    }
}
```

**복잡도**: O(E log E).
**함정**:
- 0-indexed (프로그래머스).
- 자기 자신 edge나 중복 edge가 있어도 UF가 자동 처리.

---

## 7. 함정·엣지케이스

| 함정 | 증상 | 대응 |
|---|---|---|
| **1-indexed vs 0-indexed** | OutOfBounds 또는 답이 1 빗나감 | 입력 형식 확인. 안전하게 n+1 크기 잡기 |
| **자기 자신 edge (self-loop)** | 무한루프 (DFS) 또는 indegree 1로 시작 | Kahn은 자연스럽게 사이클 처리. 다른 곳은 명시 체크 |
| **중복 edge (multi-edge)** | 그래프 정상, 알고리즘은 자동 처리 | 단, "edge 개수 = E"를 가정한 코드는 깨질 수 있음 |
| **disconnected graph** | BFS/DFS가 한 컴포넌트만 처리 | 모든 노드 순회하며 미방문이면 새로 시작 |
| **Long overflow** | 가중치 합이 int max 초과 | Dijkstra/MST에서 가중치 큰 경우 dist를 Long으로 |
| **MAX_VALUE + w overflow** | Bellman-Ford에서 음수처럼 보임 | `MAX_VALUE / 4` 사용 또는 `dist[u] != MAX_VALUE` 체크 |
| **Dijkstra에 음수 가중치** | 잘못된 답 (조용히) | 가중치 ≥ 0 확인. 음수면 Bellman-Ford |
| **stale entry 미처리** | 시간 폭증 (TLE) | `if (d > dist[u]) continue;` 필수 |
| **음수 사이클** | 최단거리 정의 불가 | Bellman-Ford로 검출 후 -1 반환 |
| **MST에 disconnected** | n-1 edge 못 채움 | picked < n-1이면 -1 |
| **Stack overflow (DFS 재귀)** | n=10^5에서 SOF | iterative DFS 또는 -Xss 증가. UF도 iterative 권장 |
| **PriorityQueue Comparator overflow** | `a[0] - b[0]`이 음수 - 큰 양수 → overflow | `Integer.compare(a[0], b[0])` 사용 |
| **인접 행렬 메모리 폭발** | n=10^5이면 80GB | 인접 리스트만. 행렬은 V ≤ 1000일 때만 |

### 7.1 PriorityQueue Comparator 오버플로우 (실전 버그)

```java
// WRONG: -2_000_000_000 - 1_000_000_000 = +1B (overflow)
new PriorityQueue<>((a, b) -> a[0] - b[0]);

// RIGHT
new PriorityQueue<>((a, b) -> Integer.compare(a[0], b[0]));
```

Dijkstra의 dist가 Long이면 더 위험. `Long.compare` 사용.

### 7.2 Bellman-Ford 음수 사이클의 "도달 가능성"

음수 사이클이 존재해도 출발점에서 그 사이클에 **도달할 수 없으면** 답은 여전히 유효하다. 단순히 "마지막 한 번 더 relax해서 갱신되면 -1" 하면 도달 불가 음수 사이클도 -1 처리해버려서 틀린다. 정밀하게 풀려면 BFS로 src에서 도달 가능한 노드 집합 안에서만 음수 사이클 검사.

---

## 8. 꼬리질문 트리

### Q1. "음수 가중치가 있을 때 Dijkstra가 실패하는 이유는?"

A: Dijkstra의 invariant는 "heap에서 pop된 dist는 최종"이다. 음수 edge가 있으면 이미 확정된 dist가 나중에 더 작아질 수 있어서 invariant가 깨진다. 보드에 반례 그리며 설명 (1.4 절 그림 사용).

### Q2. "음수 사이클은 어떻게 검출하나?"

A: Bellman-Ford로 V-1번 relax 후 한 번 더 돌렸을 때 dist가 갱신되면 음수 사이클. 단, src에서 **도달 가능한** 음수 사이클만 답에 영향. SPFA에서는 노드가 V번 이상 큐에 들어가면 음수 사이클.

### Q3. "K-shortest path (K번째 짧은 경로)는?"

A: Dijkstra 변형. 보통 노드를 방문해도 제거 안 하고, count[v] < K면 계속 처리. PriorityQueue에서 K번째로 pop되는 dist가 답. Yen's algorithm은 더 정교한 K-shortest **다른** 경로용 (LeetCode 2045 비슷).

### Q4. "Strongly Connected Component (SCC)는?"

A: 방향 그래프에서 서로 도달 가능한 노드들의 최대 부분집합.
- **Kosaraju**: DFS finish time 역순으로 reverse graph에서 DFS. 두 번 DFS.
- **Tarjan**: 한 번의 DFS로 low-link 추적. Stack 기반.
실전 응용: dependency graph 사이클 압축, 2-SAT, condensation graph (DAG로 만들기).

### Q5. "Dijkstra와 BFS의 관계?"

A: BFS는 모든 가중치가 1인 Dijkstra와 동등. 큐가 자연스럽게 거리 오름차순 보장. **0-1 BFS**는 가중치가 {0, 1}인 그래프에서 deque로 O(V+E) Dijkstra.

### Q6. "MST가 unique한가?"

A: 모든 edge weight가 distinct면 unique. 같은 weight가 있으면 여러 MST 존재 가능하지만 **MST의 총 비용은 항상 같다** (cut property).

### Q7. "방향 그래프의 MST는?"

A: Edmonds' algorithm (a.k.a. Chu-Liu/Edmonds). 각 노드의 incoming edge 중 최소를 선택하고 사이클 발생 시 축약. O(VE) 또는 O(E + V log V) (Tarjan). 면접엔 거의 안 나옴.

### Q8. "거리뿐 아니라 경로 자체를 출력하려면?"

A: `prev[v] = u`를 갱신할 때 마다 기록 → dst에서 src까지 prev 따라가며 역추적 → reverse.

### Q9. "그래프가 너무 커서 메모리 부족하면?"

A:
- 인접 리스트의 List<int[]> 대신 CSR (Compressed Sparse Row) 표현: head[], next[], to[] 배열로 link list 인라인화.
- Out-of-core: 디스크 + Bloom filter.
- 분산: Pregel, GraphX (스파크).

### Q10. "Bellman-Ford와 SPFA 차이?"

A: SPFA(Shortest Path Faster Algorithm)는 Bellman-Ford의 큐 기반 최적화. 한 번 갱신된 노드만 다시 처리. 평균은 매우 빠르지만 **최악 O(VE) 동일**. 경쟁 프로그래밍 외에는 거의 안 씀.

---

## 9. 다른 패턴과의 연결

### 9.1 BFS/DFS의 일반화

```
        BFS/DFS (08, 09장)
              │
              ▼  가중치 추가
          Dijkstra (가중치 ≥ 0)
              │
              ▼  음수 허용
        Bellman-Ford
              │
              ▼  모든 쌍
       Floyd-Warshall (DP)
```

**핵심**: 모두 "한 노드의 정보를 이웃에 전파"하는 framework. 다른 점은 어떤 순서로 전파하느냐 (FIFO vs 가중치 우선 vs 모든 edge V-1번).

### 9.2 위상정렬 = DAG의 DP 순서

DP는 "작은 부분 문제부터" 풀어야 한다. DAG에서 "작은 부분"은 topological 순서로 앞쪽. LIS, LCS도 결국 implicit DAG 위의 DP. **그래서 DP 문제가 DAG로 모델링되는 순간, 풀이는 위상정렬 + 각 노드에서 max/min 계산.**

예: LeetCode 329 Longest Increasing Path in a Matrix — 격자를 DAG로 보고 위상정렬 + DP.

### 9.3 MST = Greedy의 교과서

Kruskal/Prim 모두 greedy. **Cut property**가 증명 핵심:
> 어떤 cut(노드를 두 그룹으로 나눔)에서도, 두 그룹을 잇는 edge 중 최소 weight인 것은 어떤 MST에 반드시 포함된다.

이게 greedy 선택을 정당화. 다른 greedy 문제 (Activity Selection, Huffman) 풀 때 "왜 이 선택이 최적인가"를 비슷한 방식(exchange argument)으로 증명해야 함 → 13장 Greedy로 이어짐.

### 9.4 Union-Find = 분산 시스템 partition의 추상

- **Network partition 감지**: 노드 간 connectivity를 UF로 관리. 한쪽 root가 갈리면 partition 발생.
- **Consistent Hashing**: 노드 추가/삭제 시 영향 받는 key 그룹 = UF의 컴포넌트.
- **Image segmentation**: 픽셀을 UF로 묶어서 region 분할 (실제 알고리즘 — Felzenszwalb).

### 9.5 시니어 운영 관점 매핑

| 그래프 알고리즘 | Production 응용 |
|---|---|
| **위상정렬** | CI/CD build order, Spring Bean 의존성 해석, Kubernetes init container 순서, Maven dependency resolve |
| **사이클 검출** | Microservice circular dependency (안티 패턴), DB foreign key cycle, deadlock detection |
| **Dijkstra** | BGP/OSPF routing (Link-state는 사실상 Dijkstra), Kafka leader election의 거리 비교, Service mesh latency-aware routing (Istio Locality LB) |
| **Bellman-Ford** | RIP (distance vector routing), 환율 차익 (arbitrage) 탐지, 금융 시스템 음수 cycle = 무한 이익 의심 |
| **MST** | 네트워크 토폴로지 설계 (datacenter cable 최소화), VPN mesh 구축, cluster overlay network |
| **Union-Find** | Distributed system partition tracking, GraphQL 스키마 통합, log correlation 그룹화, Sentry issue grouping (사실상 UF) |
| **SCC** | Microservice 순환 의존 그룹 추출 (refactor target), Bayesian network condensation |
| **Floyd-Warshall** | All-pairs latency 행렬 (작은 클러스터), Game AI navmesh |

특히 **Microservice dependency graph 운영**:
1. 모든 서비스의 호출 관계를 DAG로 모델링 (cycle은 alert).
2. 위상정렬로 배포 순서 결정 (의존성 있는 쪽 먼저).
3. SCC로 "강결합" 그룹 발견 → 리팩터링 후보.
4. 장애 시 Dijkstra로 "장애 서비스에서 가장 가까운 영향 받는 서비스" 추적.

이것이 그래프 이론이 단순 알고리즘 문제를 넘어 **시스템 설계와 SRE에 직접 연결되는** 이유다.

---

## 10. 백지 마스터 체크리스트

다음을 보지 않고 작성할 수 있어야 한다.

- [ ] 인접 리스트 vs 인접 행렬 trade-off (메모리·순회 시간)
- [ ] Union-Find with path compression + union by rank — α(n) 보장
- [ ] Kahn 위상정렬 (indegree + 큐)
- [ ] DFS 기반 위상정렬 (post-order의 역순)
- [ ] Dijkstra with PriorityQueue + stale entry skip
- [ ] Bellman-Ford with snapshot (K-bounded 변형)
- [ ] Floyd-Warshall 3중 루프 (k, i, j 순서가 핵심)
- [ ] Kruskal MST (Edge 정렬 + UF)
- [ ] Prim MST (PQ 기반)
- [ ] 음수 사이클 검출 (Bellman-Ford 추가 라운드)
- [ ] 각 알고리즘이 깨지는 조건과 이유
- [ ] 1-indexed/0-indexed, Long overflow, MAX_VALUE+w overflow 함정
- [ ] 6.6 (Cheapest Flights)의 snapshot이 왜 필요한지 5초 안에 설명
- [ ] 6.9 (순위)의 Floyd가 왜 적합한지 (n ≤ 100 + reachability)
- [ ] Cut property + MST greedy 정당화

마스터 수준 = 라이브 코딩 환경에서 문제 30초 분류 → 5분 안에 정답 코드 → 함정·복잡도까지 자발적으로 언급.

---

## 11. 더 깊이 (선택)

- **Kosaraju / Tarjan SCC** — 방향 그래프의 강결합 컴포넌트
- **2-SAT** — implication graph + SCC로 충족 가능성 판정
- **Edmonds' algorithm** — 방향 그래프 MST (Arborescence)
- **A\*** — Dijkstra + heuristic. 경로 탐색 (게임, 지도)
- **Bidirectional Dijkstra** — 양쪽에서 동시 진행, 만나는 지점에서 종료
- **Johnson's algorithm** — 음수 가중치에서 모든 쌍 최단경로 (Bellman-Ford + Dijkstra 결합)
- **Network flow** — Ford-Fulkerson, Dinic. 최대 유량 / 최소 컷
- **Min-cost Max-flow** — 매칭, 할당 문제
- **Heavy-Light Decomposition** — 트리 경로 쿼리 O(log² N)
- **LCA (Lowest Common Ancestor)** — Binary Lifting, Tarjan offline

이들은 코딩 테스트보다는 ICPC/Codeforces 수준. 면접에서는 "이런 게 있다"만 알면 충분하고, **위 10개 코어 알고리즘을 백지에 막힘없이 쓰는 것**이 90% 이상이다.
