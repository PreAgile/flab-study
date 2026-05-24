# 05. Heap / Priority Queue (힙·우선순위 큐)

> "PriorityQueue는 정렬된 큐"라고 답하면 입문자. 마스터는 heap이 **shape property (complete binary tree)** + **heap order property (parent ≤/≥ children)** 두 불변식을 동시에 유지하는 array 기반 자료구조이고, build-heap이 왜 O(n)인지(삽입 n번이면 O(n log n)인데), Dijkstra가 왜 indexed heap을 원하는지, two-heap median trick이 왜 amortized O(log n)인지를 안다.
>
> 이 챕터는 옵션·문법 외우기 대신 **본질·왜·연결·라이브 코딩 통과 패턴**만 다룬다.

---

## 0. 인지 신호 — 문제에서 heap을 감지하는 키워드

이 단어/구문이 보이면 30초 안에 heap을 후보로 올린다.

| 신호 | 예시 문장 | 왜 heap인가 |
|---|---|---|
| **"K번째 큰/작은"** | "K번째로 큰 원소를 찾아라" | 전체 정렬은 O(n log n), heap은 O(n log k) |
| **"Top K"** | "가장 빈도 높은 K개 단어" | 크기 k 짜리 min-heap 유지하면 O(n log k) |
| **"최소/최대를 반복 추출"** | "가장 작은 둘을 꺼내 합쳐서 다시 넣는다" | min-heap의 정의 그 자체 (Huffman, 카드 정렬) |
| **"K개 정렬된 리스트 병합"** | "K개 sorted list를 하나로" | k-way merge → min-heap of (value, listIdx) |
| **"스트림의 중앙값"** | "데이터가 한 개씩 들어올 때마다 median 출력" | two-heap (max-heap of lower half + min-heap of upper half) |
| **"가장 무거운 돌 둘을 부딪쳐"** | LeetCode 1046 | max-heap에서 두 개 꺼내 차이 다시 push |
| **"이중 우선순위 큐"** | 프로그래머스 — max/min 둘 다 빠르게 | TreeMap 또는 two-heap |
| **"가능한 작업 중 이익 최대"** | LeetCode 502 IPO | 자본 조건 통과한 항목만 max-heap에 |
| **"실행 시간 가장 짧은 작업 먼저"** | 디스크 컨트롤러 (SJF) | min-heap of duration |
| **"우선순위 기반 스케줄링"** | Job/process scheduler | OS-level priority queue |

**핵심 직관**:
> "전체 정렬은 필요 없는데, **계속해서 최솟값/최댓값만** 뽑아야 한다" → heap.
> "K개만 기억하면 되는데, 새 값이 들어올 때 **K개 중 가장 작은(or 큰) 걸 버린다**" → 크기 K짜리 heap.

라이브 코딩에서 면접관이 "이걸 더 빠르게 할 수 있을까요?"라고 물었을 때, 정렬 풀이가 보였다면 거의 확실히 heap 풀이를 기대하는 신호다.

---

## 1. 백지 그리기 — heap의 모든 것을 한 장에

### 1.1 두 불변식 (이게 heap의 정의)

```
[Heap = Shape property + Order property]

  Shape property (complete binary tree):
     - 마지막 level 빼고 꽉 차 있음
     - 마지막 level은 왼쪽부터 채움
     - → 배열로 표현 가능 (gap 없음)

  Heap order property:
     - Min-heap: parent ≤ children (root = 최솟값)
     - Max-heap: parent ≥ children (root = 최댓값)
     - 형제끼리는 무관 (정렬되어 있지 않음 — 흔한 오해)
```

```
   Min-heap 예시 (root = 1이 최소):

              1
            /   \
           3     5
          / \   / \
         4   8 9   6
        / \
       7   10

   배열 표현 (1-based로 그리면 더 직관적):
   index:  1  2  3  4  5  6  7  8   9   10
   value:  1  3  5  4  8  9  6  7   10

   부모/자식 공식 (1-based):
     parent(i) = i / 2
     left(i)   = 2i
     right(i)  = 2i + 1

   0-based (Java PriorityQueue 내부):
     parent(i) = (i - 1) / 2
     left(i)   = 2i + 1
     right(i)  = 2i + 2
```

**왜 array인가?**
- complete binary tree라 gap이 없음 → 노드 객체/포인터 불필요 → cache locality 최고.
- index 산술로 parent/child 즉시 계산 (`2i+1`, `2i+2`).
- linked tree는 노드마다 `left/right/parent` 포인터로 메모리 24~32B 추가 + cache miss.

**왜 정렬되어 있지 않은가?**
- "heap = sorted array"는 가장 흔한 오해.
- heap은 **root만** 보장한다 (min 또는 max). 나머지는 partial order.
- 그래서 build-heap O(n)이 가능하다 (전체 정렬은 O(n log n)).

---

### 1.2 sift-up (insert 시) ASCII 단계별

```
[삽입: heap에 2 넣기]

  Step 0 — 마지막 위치에 일단 append (shape property 유지)

              1
            /   \
           3     5
          / \   / \
         4   8 9   6
        / \  \
       7  10  2     ← 새로 들어옴, 부모 8과 비교

  Step 1 — 2 < 8 → swap (부모 자리로 올라감)

              1
            /   \
           3     5
          / \   / \
         4   2 9   6
        / \  \
       7  10  8

  Step 2 — 2 < 3 (현재 부모) → swap

              1
            /   \
           2     5
          / \   / \
         4   3 9   6
        / \  \
       7  10  8

  Step 3 — 2 > 1 → 멈춤 (heap order 회복됨)

  → root까지 가도 최악 O(log n) — tree 높이만큼만 이동
```

**핵심**: sift-up은 **자식 → 부모** 방향. 한 줄에 한 단계씩 swap, 부모보다 작으면(min-heap) 계속 올라감, 크면 멈춤.

---

### 1.3 sift-down (poll 시) ASCII 단계별

```
[추출: root (1) 빼기]

  Step 0 — root 반환 후, 마지막 원소를 root로 옮긴다 (shape 유지)

              1                    [8]            ← 8을 root로
            /   \                  /   \
           2     5      →         2     5
          / \   / \              / \   / \
         4   3 9   6            4   3 9   6
        / \                    / \
       7  10                  7  10

  Step 1 — 8을 자식 둘 중 더 작은 쪽과 비교 (2 vs 5 → 2)
            8 > 2 → swap

              2
            /   \
           8     5
          / \   / \
         4   3 9   6
        / \
       7  10

  Step 2 — 8을 자식 둘 중 더 작은 쪽과 비교 (4 vs 3 → 3)
            8 > 3 → swap

              2
            /   \
           3     5
          / \   / \
         4   8 9   6
        / \
       7  10

  Step 3 — 8의 자식이 없음 → 멈춤 (leaf 도달)

  → 최악 O(log n) — leaf까지 내려갈 수 있음
```

**핵심 함정**: sift-down에서 자식 둘 다 비교 안 하면 깨진다.
- min-heap: **더 작은** 자식과 swap (그래야 그 자식이 새 부모가 되어 order 유지)
- max-heap: **더 큰** 자식과 swap

이걸 잘못하면 "분명 heap이라고 했는데 root가 최소가 아닌" 디버깅 지옥에 빠진다.

---

### 1.4 build-heap O(n) — 가장 자주 묻는 꼬리질문

```
[배열 [4, 1, 3, 2, 16, 9, 10, 14, 8, 7]을 heap으로]

  방법 A — 빈 heap에 insert n번
    각 insert = O(log n) → 총 O(n log n)

  방법 B — bottom-up heapify (이게 O(n))
    leaf는 이미 heap (자식 없음, trivially heap-order 만족)
    → 마지막 internal node부터 sift-down
    → index n/2-1, n/2-2, ..., 0 순서로
```

**왜 O(n)인가? — 증명 요약**

```
높이 h인 노드는 최대 h번 sift-down.
높이 h인 노드 개수 ≤ ⌈n / 2^(h+1)⌉

총 비용 = Σ (h=0 to log n) (n/2^(h+1)) × O(h)
       = O(n) × Σ (h/2^h)
       = O(n) × 2          ← Σ h/2^h = 2 수렴 (등비-등차 시그마)
       = O(n)

직관: leaf가 많고 (heap의 절반!), leaf는 비용 0.
     root는 비용 log n이지만 1개뿐.
     → 무거운 일은 적은 노드만, 가벼운 일은 많은 노드.
     반대로 sift-up은 leaf가 log n 비용 → O(n log n).
```

| 방식 | 비용 | 어디 쓰임 |
|---|---|---|
| insert n번 (sift-up) | O(n log n) | online: 데이터가 한 개씩 들어옴 |
| heapify n/2번 (sift-down) | **O(n)** | offline: 배열 전체가 미리 있음, Heap Sort의 첫 단계 |

라이브 코딩에서 `new PriorityQueue<>(Arrays.asList(arr))` 또는 `new PriorityQueue<>(collection)` 생성자가 O(n) heapify를 호출한다. 직접 `pq.offer()` n번 하지 말 것.

---

### 1.5 two-heap median trick (LeetCode 295)

```
[스트림의 중앙값]

  핵심 발상: 데이터를 두 덩어리로 자른다.
    lower half — max-heap (가장 큰 lower = 중앙값 후보)
    upper half — min-heap (가장 작은 upper = 중앙값 후보)

  불변식:
    1. lower.size() == upper.size()  OR  lower.size() == upper.size() + 1
    2. lower.peek() ≤ upper.peek()   (모든 lower ≤ 모든 upper)

  median:
    lower.size() > upper.size()  →  lower.peek()
    같으면                       →  (lower.peek() + upper.peek()) / 2

  add(x):
    1. lower가 비었거나 x ≤ lower.peek() → lower에 push
       아니면 → upper에 push
    2. balance: size 차이가 2면 큰 쪽 → 작은 쪽으로 이동
```

```
  스트림: 5, 2, 10, 8, 3

  add(5):
    lower(max): [5]      upper(min): []
    median = 5

  add(2):
    2 < 5 → lower에 push
    lower: [5, 2]        upper: []
    balance: lower 2개, upper 0개 → lower.poll() (5) → upper.push
    lower: [2]           upper: [5]
    median = (2 + 5) / 2 = 3.5

  add(10):
    10 > 2 → upper에 push
    lower: [2]           upper: [5, 10]
    balance: upper 2개, lower 1개 → upper.poll() (5) → lower.push
    lower: [5, 2]        upper: [10]
    median = 5

  add(8):
    8 > 5 → upper에 push
    lower: [5, 2]        upper: [8, 10]
    median = (5 + 8) / 2 = 6.5

  add(3):
    3 < 5 → lower에 push
    lower: [5, 3, 2]     upper: [8, 10]
    median = 5
```

amortized O(log n) per add — 매 add마다 push 1번 + 가능하면 poll/push 한 쌍.

---

## 2. 직관과 정의

### 2.1 한 줄 비유

> **응급실 트리아지** — 환자가 도착해도 도착 순서대로가 아니라 **위중도 순서대로** 진료한다. 새 환자가 들어오면 위중도에 따라 끼워 넣고, 다음 환자는 항상 "가장 위중한 사람". 이게 priority queue. 응급실 컴퓨터가 환자 1000명 명단을 매번 정렬하지 않는 이유 = heap 자료구조.

### 2.2 정확한 정의

**Priority Queue (ADT)**: 다음 연산을 지원하는 추상 자료형.
- `insert(x, priority)` — 원소 삽입
- `extractMin()` 또는 `extractMax()` — 최고 우선순위 원소 제거 + 반환
- `peek()` — 제거 없이 조회

**Binary Heap**: 위 ADT를 구현하는 자료구조 중 하나 (가장 흔함).
- 다른 구현: TreeMap (BBST), Fibonacci heap (decrease-key O(1) amortized), pairing heap, leftist tree …
- Java `PriorityQueue` = binary min-heap (array 기반, 0-indexed).

**Heap ≠ Priority Queue**: heap은 자료구조, PQ는 ADT. Java/Kotlin 코드에서는 거의 동의어로 쓰지만 면접에서 헷갈리면 감점.

### 2.3 Java `PriorityQueue` 내부 구조

```
[java.util.PriorityQueue (OpenJDK 17 기준)]

  field:
    Object[] queue          ← heap 배열 (0-based)
    int size
    Comparator<? super E> comparator    ← null이면 natural order
    int modCount            ← fail-fast iteration용

  offer(e):
    if (size == queue.length) grow(size + 1);   ← 50% 확장
    siftUp(size, e);
    size++;

  poll():
    E result = (E) queue[0];
    E x = (E) queue[--size];
    queue[size] = null;            ← help GC
    if (size != 0) siftDown(0, x);
    return result;

  생성자 PriorityQueue(Collection c):
    queue = c.toArray();
    heapify();                     ← O(n) bottom-up sift-down
```

**중요**:
- `iterator()`는 **heap 순서**로 순회, **정렬 순서가 아님**. for-each로 출력해서 정렬됐는지 확인하면 안 됨.
- thread-safe 아님. 동시성 필요하면 `PriorityBlockingQueue` (unbounded, ReentrantLock 기반).
- `remove(Object)` O(n) — 임의 원소 제거는 비효율. 필요하면 별도 indexed heap 자체 구현.

---

## 3. Java 템플릿

### 3.1 Min-heap (기본 — natural ordering)

```java
import java.util.PriorityQueue;

PriorityQueue<Integer> minHeap = new PriorityQueue<>();
minHeap.offer(5);
minHeap.offer(1);
minHeap.offer(3);
minHeap.peek();   // 1
minHeap.poll();   // 1
minHeap.poll();   // 3
minHeap.poll();   // 5
```

`Integer`, `String`, `Long` 등 `Comparable` 구현체는 자동으로 natural ordering (오름차순).

### 3.2 Max-heap (역순)

```java
// 방법 1: Comparator.reverseOrder()
PriorityQueue<Integer> maxHeap = new PriorityQueue<>(Comparator.reverseOrder());

// 방법 2: lambda (자주 씀)
PriorityQueue<Integer> maxHeap2 = new PriorityQueue<>((a, b) -> b - a);
//                                                              ^^^^^
//                                                    overflow 위험! 아래 함정 참고

// 방법 3: Integer.compare (안전)
PriorityQueue<Integer> maxHeap3 = new PriorityQueue<>((a, b) -> Integer.compare(b, a));
```

**왜 `b - a`가 위험한가?**
- `a = Integer.MAX_VALUE`, `b = -1` → `b - a = -1 - Integer.MAX_VALUE` overflow → 양수 됨 → 비교 뒤집힘 → heap 깨짐.
- 라이브 코딩에서 "어차피 값이 작으니까"라고 넘기지 말 것. 면접관이 짚는다.

### 3.3 커스텀 객체 (Comparator)

```java
record Task(int priority, String name) {}

// priority 오름차순 (낮은 priority = 먼저 처리)
PriorityQueue<Task> pq = new PriorityQueue<>(Comparator.comparingInt(Task::priority));

// 복합 정렬: priority 오름 → 이름 사전순
PriorityQueue<Task> pq2 = new PriorityQueue<>(
    Comparator.comparingInt(Task::priority)
              .thenComparing(Task::name)
);

// priority 내림 → 이름 사전 역순
PriorityQueue<Task> pq3 = new PriorityQueue<>(
    Comparator.comparingInt(Task::priority).reversed()
              .thenComparing(Comparator.comparing(Task::name).reversed())
);
```

`Comparator.comparingInt`가 `comparing` 보다 빠르다 — primitive int 비교라 boxing 없음. long은 `comparingLong`.

### 3.4 Two-heap (median tracker)

```java
class MedianFinder {
    private final PriorityQueue<Integer> lower = new PriorityQueue<>(Comparator.reverseOrder()); // max-heap
    private final PriorityQueue<Integer> upper = new PriorityQueue<>();                          // min-heap

    public void addNum(int num) {
        if (lower.isEmpty() || num <= lower.peek()) lower.offer(num);
        else upper.offer(num);

        // rebalance: |size 차| ≤ 1
        if (lower.size() > upper.size() + 1) upper.offer(lower.poll());
        else if (upper.size() > lower.size()) lower.offer(upper.poll());
    }

    public double findMedian() {
        if (lower.size() > upper.size()) return lower.peek();
        return (lower.peek() + upper.peek()) / 2.0;
    }
}
```

### 3.5 K-way merge (LeetCode 23 패턴)

```java
class ListNode {
    int val;
    ListNode next;
    ListNode(int v) { val = v; }
}

public ListNode mergeKLists(ListNode[] lists) {
    PriorityQueue<ListNode> pq = new PriorityQueue<>(Comparator.comparingInt(n -> n.val));
    for (ListNode head : lists) {
        if (head != null) pq.offer(head);
    }

    ListNode dummy = new ListNode(0);
    ListNode tail = dummy;
    while (!pq.isEmpty()) {
        ListNode min = pq.poll();
        tail.next = min;
        tail = min;
        if (min.next != null) pq.offer(min.next);
    }
    return dummy.next;
}
```

heap size = K (리스트 개수), 총 노드 N → O(N log K). 모든 노드 단순 합쳐 정렬하면 O(N log N) — K가 작을 때 heap 풀이가 압도적.

### 3.6 Top K — 크기 K 짜리 min-heap (Top K **largest**)

```java
public int[] topKLargest(int[] nums, int k) {
    PriorityQueue<Integer> minHeap = new PriorityQueue<>(k);
    for (int n : nums) {
        minHeap.offer(n);
        if (minHeap.size() > k) minHeap.poll();   // 가장 작은 거 버림
    }
    // 남은 K개가 top K largest (정렬 순서는 보장 안 됨)
    int[] res = new int[k];
    for (int i = 0; i < k; i++) res[i] = minHeap.poll();
    return res;
}
```

**왜 max-heap이 아니라 min-heap?**
- top K **largest**를 원함 → heap의 root는 "지금까지 본 K개 중 **가장 작은**" 것이어야 새 값이 들어왔을 때 root만 비교해서 버릴지 결정할 수 있음.
- root가 max였다면 새 값이 작아도 들어와야 할지 비교 비용이 큼.
- 직관: **반대 종류의 heap**을 써야 "임계 원소만 보고 결정"이 된다.

top K **smallest** → max-heap of size K. 헷갈리면 항상 "내가 버리고 싶은 게 root여야 한다"로 외운다.

---

## 4. Kotlin 템플릿

Kotlin에는 `PriorityQueue` 전용 클래스가 없다. `java.util.PriorityQueue`를 그대로 쓴다.

### 4.1 기본 사용

```kotlin
import java.util.PriorityQueue

val minHeap = PriorityQueue<Int>()
minHeap.offer(5)
minHeap.offer(1)
minHeap.offer(3)
println(minHeap.peek())   // 1
println(minHeap.poll())   // 1
```

### 4.2 Max-heap

```kotlin
// 방법 1: reverseOrder()
val maxHeap = PriorityQueue<Int>(compareByDescending { it })

// 방법 2: Comparator
val maxHeap2 = PriorityQueue<Int>(Comparator.reverseOrder())

// 방법 3: 람다 (overflow 안전)
val maxHeap3 = PriorityQueue<Int> { a, b -> b.compareTo(a) }
```

### 4.3 커스텀 객체

```kotlin
data class Task(val priority: Int, val name: String)

val pq = PriorityQueue<Task>(compareBy { it.priority })

// 복합 정렬
val pq2 = PriorityQueue<Task>(
    compareBy<Task> { it.priority }.thenBy { it.name }
)

// 내림차순 + 동률 시 이름 역순
val pq3 = PriorityQueue<Task>(
    compareByDescending<Task> { it.priority }.thenByDescending { it.name }
)
```

`compareBy`, `compareByDescending`, `thenBy`, `thenByDescending` — Kotlin stdlib의 가독성 좋은 Comparator 빌더.

### 4.4 Pair / IntArray 우선순위

```kotlin
// (거리, 노드) — Dijkstra 패턴
val pq = PriorityQueue<IntArray>(compareBy { it[0] })
pq.offer(intArrayOf(0, source))

// Pair<Int, Int>
val pq2 = PriorityQueue<Pair<Int, Int>>(compareBy { it.first })

// Triple
val pq3 = PriorityQueue<Triple<Int, Int, Int>>(compareBy({ it.first }, { it.second }))
```

`IntArray`가 `Pair<Int, Int>`보다 빠르다 — boxing 없음. 라이브 코딩에서 시간 빠듯하면 `IntArray`.

### 4.5 Two-heap (Kotlin)

```kotlin
class MedianFinder {
    private val lower = PriorityQueue<Int>(compareByDescending { it })   // max-heap
    private val upper = PriorityQueue<Int>()                             // min-heap

    fun addNum(num: Int) {
        if (lower.isEmpty() || num <= lower.peek()) lower.offer(num)
        else upper.offer(num)

        when {
            lower.size > upper.size + 1 -> upper.offer(lower.poll())
            upper.size > lower.size     -> lower.offer(upper.poll())
        }
    }

    fun findMedian(): Double =
        if (lower.size > upper.size) lower.peek().toDouble()
        else (lower.peek() + upper.peek()) / 2.0
}
```

---

## 5. 시간/공간 복잡도

| 연산 | 비용 | 근거 |
|---|---|---|
| `peek()` | O(1) | root는 `queue[0]` |
| `offer(e)` / `add(e)` | O(log n) | sift-up = tree 높이 |
| `poll()` / `remove()` | O(log n) | sift-down = tree 높이 |
| `contains(o)` | O(n) | array 선형 검색 |
| `remove(Object)` | O(n) | 찾기 O(n) + sift-down O(log n) |
| `size()` | O(1) | 필드 |
| 생성자(Collection) — heapify | **O(n)** | 위 1.4 증명 |
| 생성자(n번 offer) | O(n log n) | sift-up n번 |
| iteration | O(n) | heap 순서, 정렬 X |

**공간**: O(n) — array 그 자체.

**Top K 패턴**: 크기 K짜리 heap을 유지하며 N개 처리 → **O(N log K)**, 공간 O(K). N >> K일 때 전체 정렬 O(N log N)보다 압도적 + 메모리 절약 (스트리밍 가능).

**Heap Sort**: build-heap O(n) + poll n번 O(n log n) = **O(n log n)**, in-place 가능, 하지만 cache 비친화적이라 실제 quicksort/mergesort보다 느림. Java의 `Arrays.sort`는 dual-pivot quicksort/Timsort, heap sort 안 씀.

---

## 6. 대표 문제 (6개 이상 풀이)

### 6.1 LeetCode 215 — Kth Largest Element in an Array

**문제**: 정렬되지 않은 배열 `nums`와 정수 `k`가 주어진다. K번째로 큰 원소를 반환하라.

**접근 비교**:

| 방법 | 시간 | 공간 | 특징 |
|---|---|---|---|
| 전체 정렬 후 `nums[n-k]` | O(n log n) | O(1) | 간단하지만 비효율 |
| 크기 K **min-heap** | O(n log K) | O(K) | 스트리밍 가능, 메모리 절약 |
| Quickselect (Hoare) | 평균 O(n), 최악 O(n²) | O(1) | 평균 최고, 최악 주의 |
| Quickselect + random pivot | 기대 O(n) | O(1) | 실전 정답 |

**Java — min-heap 풀이**:

```java
public int findKthLargest(int[] nums, int k) {
    PriorityQueue<Integer> minHeap = new PriorityQueue<>(k);
    for (int n : nums) {
        minHeap.offer(n);
        if (minHeap.size() > k) minHeap.poll();
    }
    return minHeap.peek();   // 크기 K짜리 min-heap의 root = K번째 큰 값
}
```

**Kotlin**:

```kotlin
fun findKthLargest(nums: IntArray, k: Int): Int {
    val minHeap = PriorityQueue<Int>()
    for (n in nums) {
        minHeap.offer(n)
        if (minHeap.size > k) minHeap.poll()
    }
    return minHeap.peek()
}
```

**복잡도**: 시간 O(n log k), 공간 O(k).

**Quickselect 대안 (꼬리질문 대비)**:

```java
public int findKthLargest(int[] nums, int k) {
    int target = nums.length - k;   // K번째 큰 = 오름차순 정렬 시 (n-k) 인덱스
    int lo = 0, hi = nums.length - 1;
    Random rng = new Random();
    while (lo < hi) {
        int p = lo + rng.nextInt(hi - lo + 1);   // random pivot — 최악 O(n²) 방지
        int idx = partition(nums, lo, hi, p);
        if (idx == target) return nums[idx];
        else if (idx < target) lo = idx + 1;
        else hi = idx - 1;
    }
    return nums[lo];
}

private int partition(int[] a, int lo, int hi, int pivotIdx) {
    int pivot = a[pivotIdx];
    swap(a, pivotIdx, hi);
    int store = lo;
    for (int i = lo; i < hi; i++) {
        if (a[i] < pivot) swap(a, i, store++);
    }
    swap(a, store, hi);
    return store;
}

private void swap(int[] a, int i, int j) { int t = a[i]; a[i] = a[j]; a[j] = t; }
```

면접관이 "더 빠르게?"라고 물으면 **quickselect**. "스트리밍이라면?" 또는 "메모리 제한 있다면?" 물으면 **heap**.

**함정**: K = nums.length일 때 (모든 원소 다 들어옴) → 정상 동작 확인 필요. 빈 배열은 보통 입력 보장.

---

### 6.2 LeetCode 347 — Top K Frequent Elements

**문제**: 정수 배열 `nums`와 `k`가 주어진다. 빈도 상위 K개 원소를 반환하라.

**접근**:
1. HashMap으로 빈도 카운트 — O(n)
2. 빈도 기준 min-heap of size K — O(n log k)
3. 답: heap에서 모두 poll — O(k log k)

**Java**:

```java
public int[] topKFrequent(int[] nums, int k) {
    Map<Integer, Integer> freq = new HashMap<>();
    for (int n : nums) freq.merge(n, 1, Integer::sum);

    // 빈도 오름차순 min-heap (root = 가장 빈도 낮은 = 버릴 후보)
    PriorityQueue<int[]> minHeap = new PriorityQueue<>(Comparator.comparingInt(a -> a[1]));
    for (var e : freq.entrySet()) {
        minHeap.offer(new int[]{e.getKey(), e.getValue()});
        if (minHeap.size() > k) minHeap.poll();
    }

    int[] result = new int[k];
    for (int i = k - 1; i >= 0; i--) result[i] = minHeap.poll()[0];
    return result;
}
```

**Kotlin**:

```kotlin
fun topKFrequent(nums: IntArray, k: Int): IntArray {
    val freq = HashMap<Int, Int>()
    for (n in nums) freq[n] = (freq[n] ?: 0) + 1

    val minHeap = PriorityQueue<IntArray>(compareBy { it[1] })
    for ((num, count) in freq) {
        minHeap.offer(intArrayOf(num, count))
        if (minHeap.size > k) minHeap.poll()
    }
    return IntArray(k) { minHeap.poll()[0] }.also { it.reverse() }
}
```

**복잡도**: 시간 O(n log k), 공간 O(n + k).

**대안 — bucket sort**: 빈도가 1..n 범위이므로 buckets[freq] = list of nums → 뒤에서부터 K개 → **O(n)**. K가 클 때 heap보다 빠름. 면접에서 꼬리질문으로 자주.

**함정**: 순서는 보통 unordered (문제 명세 확인). LeetCode는 순서 무관.

---

### 6.3 LeetCode 23 — Merge K Sorted Lists

**문제**: K개의 정렬된 linked list를 하나의 정렬된 linked list로 병합.

**접근**: heap에 각 list의 head만 일단 넣어둠. poll할 때마다 다음 노드를 push.

**Java**:

```java
public ListNode mergeKLists(ListNode[] lists) {
    if (lists == null || lists.length == 0) return null;

    PriorityQueue<ListNode> pq = new PriorityQueue<>(Comparator.comparingInt(n -> n.val));
    for (ListNode head : lists) {
        if (head != null) pq.offer(head);
    }

    ListNode dummy = new ListNode(0), tail = dummy;
    while (!pq.isEmpty()) {
        ListNode node = pq.poll();
        tail.next = node;
        tail = node;
        if (node.next != null) pq.offer(node.next);
    }
    return dummy.next;
}
```

**Kotlin**:

```kotlin
fun mergeKLists(lists: Array<ListNode?>): ListNode? {
    val pq = PriorityQueue<ListNode>(compareBy { it.`val` })
    for (head in lists) if (head != null) pq.offer(head)

    val dummy = ListNode(0)
    var tail: ListNode = dummy
    while (pq.isNotEmpty()) {
        val node = pq.poll()
        tail.next = node
        tail = node
        if (node.next != null) pq.offer(node.next!!)
    }
    return dummy.next
}
```

**복잡도**: 시간 **O(N log K)** (N = 전체 노드 수), 공간 O(K).

**대안 — divide & conquer**: 두 리스트씩 짝지어 병합. log K 단계, 각 단계 O(N) → 같은 O(N log K), 공간 O(log K) recursion stack. 실전에서는 heap이 더 직관적이고 깔끔.

**함정**:
- 빈 리스트 (`null`) 입력 — 체크 필요.
- 전체 빈 입력 → `dummy.next == null` 자연스럽게 처리됨.
- Comparator로 `n -> n.val` 람다 만들 때 `n` 이 null일 수 없도록 위에서 미리 거름.

---

### 6.4 LeetCode 295 — Find Median from Data Stream

**문제**: 정수 스트림에서 매번 중앙값을 반환.

**접근**: two-heap (1.5절 그대로).

**Java**:

```java
class MedianFinder {
    private final PriorityQueue<Integer> lower = new PriorityQueue<>(Comparator.reverseOrder());
    private final PriorityQueue<Integer> upper = new PriorityQueue<>();

    public void addNum(int num) {
        if (lower.isEmpty() || num <= lower.peek()) lower.offer(num);
        else upper.offer(num);

        if (lower.size() > upper.size() + 1) upper.offer(lower.poll());
        else if (upper.size() > lower.size()) lower.offer(upper.poll());
    }

    public double findMedian() {
        if (lower.size() > upper.size()) return lower.peek();
        return (lower.peek() + upper.peek()) / 2.0;
    }
}
```

**Kotlin**: 4.5절 참조.

**복잡도**: `addNum` O(log n), `findMedian` O(1), 공간 O(n).

**꼬리질문 단골**:
- "stream의 99%가 0..100 사이면 더 빠르게?" → bucket counter 100개 + running count, O(1) median.
- "sliding window median이라면?" → multi-set (TreeMap) 또는 두 개의 lazy-delete heap. heap만으로는 어려움 (임의 삭제 비효율).

**함정**: `(lower.peek() + upper.peek()) / 2` 정수 나눗셈 X. **`/ 2.0`** 명시. 또한 두 정수 합이 `Integer.MAX_VALUE` 근처면 overflow — `((long) lower.peek() + upper.peek()) / 2.0`이 안전.

---

### 6.5 LeetCode 502 — IPO

**문제**: 초기 자본 `w`, 최대 `k`개 프로젝트 선택 가능. 각 프로젝트는 (capital 요구, profit). 자본 충분한 것만 시작 가능, 끝나면 profit이 자본에 더해짐. 최대 자본은?

**접근** (전형적인 "두 개의 heap" 트릭):
1. 모든 프로젝트를 capital 오름차순 정렬 (또는 min-heap of capital).
2. 현재 자본으로 가능한 모든 프로젝트를 **profit max-heap**에 옮겨놓음.
3. profit max-heap에서 가장 이익 높은 것 poll → 자본 증가.
4. K번 반복.

**Java**:

```java
public int findMaximizedCapital(int k, int w, int[] profits, int[] capital) {
    int n = profits.length;
    // (capital, profit) — capital 오름차순 min-heap
    PriorityQueue<int[]> byCapital = new PriorityQueue<>(Comparator.comparingInt(a -> a[0]));
    for (int i = 0; i < n; i++) byCapital.offer(new int[]{capital[i], profits[i]});

    // profit 내림차순 max-heap
    PriorityQueue<Integer> byProfit = new PriorityQueue<>(Comparator.reverseOrder());

    for (int i = 0; i < k; i++) {
        // 자본 충분한 것 모두 옮김
        while (!byCapital.isEmpty() && byCapital.peek()[0] <= w) {
            byProfit.offer(byCapital.poll()[1]);
        }
        if (byProfit.isEmpty()) break;   // 시작 가능한 게 없음
        w += byProfit.poll();
    }
    return w;
}
```

**Kotlin**:

```kotlin
fun findMaximizedCapital(k: Int, W: Int, profits: IntArray, capital: IntArray): Int {
    var w = W
    val byCapital = PriorityQueue<IntArray>(compareBy { it[0] })
    for (i in profits.indices) byCapital.offer(intArrayOf(capital[i], profits[i]))

    val byProfit = PriorityQueue<Int>(compareByDescending { it })

    repeat(k) {
        while (byCapital.isNotEmpty() && byCapital.peek()[0] <= w) {
            byProfit.offer(byCapital.poll()[1])
        }
        if (byProfit.isEmpty()) return w
        w += byProfit.poll()
    }
    return w
}
```

**복잡도**: 시간 O((n + k) log n), 공간 O(n).

**핵심 통찰**: greedy + heap. "현재 가용한 후보 중 최고만 뽑는다" 패턴. 실전 스케줄링/광고 입찰/리소스 할당과 동형.

**함정**: profit이 음수일 수도 있나? — LeetCode 명세는 `profit ≥ 0`. 음수면 greedy 깨질 가능성 (지금 음수 가져가서 자본 줄이고 나중에 큰 거 하나 더 가능?) → 일반적으로 안 함.

---

### 6.6 LeetCode 1046 — Last Stone Weight

**문제**: 돌 무게 배열에서, 가장 무거운 두 돌을 부딪침. 둘 다 같으면 사라짐, 다르면 차이만큼 돌이 남음. 마지막에 남은 돌의 무게 (없으면 0).

**접근**: 정확히 max-heap을 위해 만들어진 문제.

**Java**:

```java
public int lastStoneWeight(int[] stones) {
    PriorityQueue<Integer> maxHeap = new PriorityQueue<>(Comparator.reverseOrder());
    for (int s : stones) maxHeap.offer(s);

    while (maxHeap.size() > 1) {
        int y = maxHeap.poll();   // 가장 큰
        int x = maxHeap.poll();   // 두 번째로 큰
        if (y != x) maxHeap.offer(y - x);
    }
    return maxHeap.isEmpty() ? 0 : maxHeap.peek();
}
```

**Kotlin**:

```kotlin
fun lastStoneWeight(stones: IntArray): Int {
    val maxHeap = PriorityQueue<Int>(compareByDescending { it })
    for (s in stones) maxHeap.offer(s)

    while (maxHeap.size > 1) {
        val y = maxHeap.poll()
        val x = maxHeap.poll()
        if (y != x) maxHeap.offer(y - x)
    }
    return if (maxHeap.isEmpty()) 0 else maxHeap.peek()
}
```

**복잡도**: 시간 O(n log n) (최악 n-1번 충돌, 각 O(log n)), 공간 O(n).

**최적화 (꼬리질문)**: stones 범위가 1..1000으로 작으면 counting sort 기반으로 O(n + max) 가능. 면접에서는 heap 풀이로 충분.

**함정**: `y - x == 0`이면 push 안 함. 안 그러면 heap에 0이 쌓여 답 망가짐.

---

### 6.7 프로그래머스 — 더 맵게

**문제**: 스코빌 지수 배열. 가장 안 매운 두 개를 `a + b * 2`로 섞음. 모든 음식이 K 이상이 되도록 최소 횟수. 불가능이면 `-1`.

**Java**:

```java
import java.util.PriorityQueue;

public class Solution {
    public int solution(int[] scoville, int K) {
        PriorityQueue<Long> pq = new PriorityQueue<>();   // long으로 overflow 방어
        for (int s : scoville) pq.offer((long) s);

        int count = 0;
        while (pq.peek() < K) {
            if (pq.size() < 2) return -1;
            long a = pq.poll();
            long b = pq.poll();
            pq.offer(a + b * 2);
            count++;
        }
        return count;
    }
}
```

**Kotlin**:

```kotlin
import java.util.PriorityQueue

class Solution {
    fun solution(scoville: IntArray, K: Int): Int {
        val pq = PriorityQueue<Long>()
        for (s in scoville) pq.offer(s.toLong())

        var count = 0
        while (pq.peek() < K) {
            if (pq.size < 2) return -1
            val a = pq.poll()
            val b = pq.poll()
            pq.offer(a + b * 2)
            count++
        }
        return count
    }
}
```

**복잡도**: O(n log n).

**함정**:
- `scoville`이 처음부터 모두 K 이상 → while 진입 X → 0 반환. OK.
- 하나 남았는데 그게 K 미만이면 `-1`. `size < 2` 체크가 필수 — 안 하면 NoSuchElementException.
- `b * 2`가 int overflow 가능 → `long` 사용. 문제 명세상 안전한 경우도 있지만 안전한 코드가 면접 +1.

---

### 6.8 프로그래머스 — 디스크 컨트롤러

**문제**: `[요청 시각, 소요 시간]` 작업 리스트. SJF (Shortest Job First) 스케줄링 시 평균 대기 시간 (소수점 버림).

**접근**:
1. 요청 시각 오름차순 정렬.
2. 현재 시각에 도착한 작업들을 **소요 시간 min-heap**에 옮김.
3. heap에서 가장 짧은 작업 실행, 시각 += 소요시간, 대기시간 누적.
4. heap 비면 다음 작업의 요청 시각으로 점프.

**Java**:

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.PriorityQueue;

public class Solution {
    public int solution(int[][] jobs) {
        Arrays.sort(jobs, Comparator.comparingInt(a -> a[0]));   // 요청 시각 순
        PriorityQueue<int[]> pq = new PriorityQueue<>(Comparator.comparingInt(a -> a[1]));

        int time = 0, idx = 0, total = 0;
        int n = jobs.length;
        while (idx < n || !pq.isEmpty()) {
            while (idx < n && jobs[idx][0] <= time) pq.offer(jobs[idx++]);
            if (pq.isEmpty()) {
                time = jobs[idx][0];
            } else {
                int[] job = pq.poll();
                time += job[1];
                total += time - job[0];   // 종료 시각 - 요청 시각 = 대기 + 처리
            }
        }
        return total / n;
    }
}
```

**Kotlin**:

```kotlin
import java.util.PriorityQueue

class Solution {
    fun solution(jobs: Array<IntArray>): Int {
        jobs.sortBy { it[0] }
        val pq = PriorityQueue<IntArray>(compareBy { it[1] })

        var time = 0
        var idx = 0
        var total = 0
        val n = jobs.size
        while (idx < n || pq.isNotEmpty()) {
            while (idx < n && jobs[idx][0] <= time) pq.offer(jobs[idx++])
            if (pq.isEmpty()) {
                time = jobs[idx][0]
            } else {
                val job = pq.poll()
                time += job[1]
                total += time - job[0]
            }
        }
        return total / n
    }
}
```

**복잡도**: O(n log n).

**핵심 통찰**: "현재 가용한 작업 중 가장 짧은 것" — 6.5 IPO와 동일한 "이중 헤프 / 정렬 + 가용 풀" 패턴. 이 패턴이 실제 OS 스케줄러 (CFS 일부, BFS), DB transaction scheduler, K8s pod scheduling priority queue의 핵심.

---

### 6.9 프로그래머스 — 이중우선순위큐

**문제**: `I n` = n 삽입, `D 1` = 최댓값 삭제, `D -1` = 최솟값 삭제. 최종 [max, min] 반환 (비었으면 [0, 0]).

**접근 A (two-heap + lazy delete)**:
- max-heap과 min-heap을 동시에 유지.
- 삽입 시 동시에 두 heap에 push + version/exists 맵 관리.
- "이미 지워졌으면 무시" 처리.

**접근 B (TreeMap)**: 가장 깔끔. `firstKey()`, `lastKey()` O(log n), 중복은 count로.

**Java — TreeMap 풀이 (권장)**:

```java
import java.util.TreeMap;

public class Solution {
    public int[] solution(String[] operations) {
        TreeMap<Integer, Integer> map = new TreeMap<>();   // value → count
        int size = 0;

        for (String op : operations) {
            String[] parts = op.split(" ");
            int x = Integer.parseInt(parts[1]);
            if (parts[0].equals("I")) {
                map.merge(x, 1, Integer::sum);
                size++;
            } else if (size > 0) {
                int key = (x == 1) ? map.lastKey() : map.firstKey();
                if (map.get(key) == 1) map.remove(key);
                else map.merge(key, -1, Integer::sum);
                size--;
            }
        }
        return size == 0 ? new int[]{0, 0} : new int[]{map.lastKey(), map.firstKey()};
    }
}
```

**Kotlin**:

```kotlin
import java.util.TreeMap

class Solution {
    fun solution(operations: Array<String>): IntArray {
        val map = TreeMap<Int, Int>()
        var size = 0

        for (op in operations) {
            val parts = op.split(" ")
            val x = parts[1].toInt()
            if (parts[0] == "I") {
                map.merge(x, 1) { a, b -> a + b }
                size++
            } else if (size > 0) {
                val key = if (x == 1) map.lastKey() else map.firstKey()
                if (map[key] == 1) map.remove(key) else map.merge(key, -1) { a, b -> a + b }
                size--
            }
        }
        return if (size == 0) intArrayOf(0, 0) else intArrayOf(map.lastKey(), map.firstKey())
    }
}
```

**복잡도**: O(n log n).

**왜 단일 heap만으로는 어려운가?**: `PriorityQueue`는 한쪽 끝만 효율적이다. 양쪽 모두 효율적이려면 **double-ended priority queue** (min-max heap, interval heap, deap) 필요 — 표준 라이브러리에 없음. → TreeMap이 가장 실용적.

**lazy delete 변형 (heap 두 개)**: 면접관이 "heap만 써서"라고 강제하면 사용.
- maxPQ, minPQ 동시 유지.
- exists 카운터 HashMap.
- poll 시 `while (peek == 카운터 0인 값) poll`로 좀비 제거.

---

## 7. 함정·엣지케이스

### 7.1 빈 큐 — `peek()`/`poll()`의 차이

```java
PriorityQueue<Integer> pq = new PriorityQueue<>();
pq.peek();    // null (예외 X)
pq.poll();    // null (예외 X)
pq.element(); // NoSuchElementException!
pq.remove();  // NoSuchElementException!
```

`peek`/`poll`은 null 반환, `element`/`remove`는 예외. 라이브 코딩에서 일관성을 위해 `peek`/`poll`만 쓰는 걸 추천. null 반환을 검사하지 않으면 NPE.

### 7.2 `b - a` overflow

```java
// 위험: Integer.MAX_VALUE와 음수 비교 시 overflow
PriorityQueue<Integer> bad = new PriorityQueue<>((a, b) -> b - a);

// 안전: Integer.compare는 long 연산으로 안전
PriorityQueue<Integer> good = new PriorityQueue<>((a, b) -> Integer.compare(b, a));

// 또는
PriorityQueue<Integer> good2 = new PriorityQueue<>(Comparator.reverseOrder());
```

같은 함정이 `Arrays.sort`, `Collections.sort`에서도 발생. **Java에서 정수 비교는 무조건 `Integer.compare`**.

### 7.3 동률 (우선순위 같을 때) — 안정성

heap은 **stable하지 않다**. 같은 우선순위 원소들의 상대 순서가 들어온 순서와 같지 않을 수 있음. FIFO 보장이 필요하면 `(priority, sequenceNumber)` tuple로 풀이.

```java
class Task {
    int priority;
    long seq;   // 들어온 순서 (외부 카운터로 증가)
}

PriorityQueue<Task> pq = new PriorityQueue<>(
    Comparator.<Task>comparingInt(t -> t.priority)
              .thenComparingLong(t -> t.seq)
);
```

라이브 코딩에서 면접관이 "동률은 어떻게?"라고 물으면, 안정성 필요 여부를 먼저 확인하고 위 패턴을 제시.

### 7.4 mutable key 변경

heap에 들어간 객체의 priority 필드를 외부에서 바꾸면 heap order property 깨짐 — 영원히 깨진 상태로 동작 (재정렬 안 됨). `pq.remove(obj)` + `pq.offer(modified)` 또는 indexed heap (decrease-key) 사용. **immutable 원소를 권장**.

### 7.5 `contains` / `remove(Object)`는 O(n)

```java
pq.contains(x);     // O(n) 선형 검색
pq.remove(x);       // O(n) — 찾기 O(n) + sift-down O(log n)
```

Dijkstra의 "decrease-key" 트릭 (lazy 방식): 큐에 (dist, node) 다시 push, poll할 때 `if (dist > best[node]) continue`로 stale entry 스킵. 깔끔하지만 큐가 커짐 → indexed heap이 진짜 해법.

### 7.6 K > N

- K가 배열 크기보다 클 때 명세 확인 필수.
- LeetCode 215 Kth Largest: K ≤ N 보장.
- "Top K"라 했는데 K > N이면 그냥 전부 반환?

### 7.7 큐 크기 vs heap order 헷갈림

```java
// 안 됨 — heap order로 iterate (정렬 X)
for (Integer x : pq) System.out.println(x);

// 정렬 순서로 모두 보려면 poll 반복
while (!pq.isEmpty()) System.out.println(pq.poll());
```

라이브 코딩에서 디버깅용 출력으로 for-each 쓰다가 "왜 정렬 안 됐지?" 5분 날린다.

### 7.8 `PriorityQueue(int initialCapacity)` 초기 용량

heap이 커지면 array가 grow (50% 확장). 미리 크기 알면 초기 용량 지정 → resize 비용 절약. 라이브 코딩에서 영향 미미하지만 production에서 hot path는 의미 있음.

---

## 8. 꼬리질문 트리 — 면접관이 던질 진짜 질문

### Q1. "Top K를 heap 말고 더 빠르게?"

**A**: Quickselect — 평균 O(n), 최악 O(n²). **median-of-medians**로 최악 O(n) 보장 (BFPRT 알고리즘) — 이론적, 실전엔 상수 커서 잘 안 씀. random pivot quickselect가 실용 정답.

```
heap:        O(n log k), 메모리 O(k), 스트리밍 가능
quickselect: 평균 O(n), 메모리 O(1), in-place 가능
```

**선택 기준**: 메모리/스트리밍 → heap, 단일 정적 배열 + 속도 최우선 → quickselect.

### Q2. "Heap vs sorted array 차이?"

| | sorted array | heap |
|---|---|---|
| insert | O(n) (자리 찾기 O(log n) + shift O(n)) | O(log n) |
| extract min/max | O(1) (양 끝) | O(log n) (root + sift-down) |
| build | O(n log n) | **O(n)** |
| memory | O(n) | O(n) (overhead 같음) |
| random access by rank | O(1) | O(n) |

→ "한 번 만들고 K번째만 자주 찾는다" → sorted array. "계속 변하면서 최솟값만 뽑는다" → heap.

### Q3. "Indexed heap이 뭔가요? Dijkstra의 decrease-key?"

```
일반 heap: 원소 위치를 모르니 decrease-key가 O(n) (선형 검색)
indexed heap: HashMap<key, index> 동기 유지 → O(log n) decrease-key

Dijkstra:
  - lazy 방식 (LeetCode 표준): stale entry 무시, 큐 크기 O(E)
  - indexed heap: 큐 크기 O(V), 정확히 한 entry per node

복잡도:
  lazy:     O((V + E) log V) — 큐 entry 최대 E개
  indexed:  O((V + E) log V) — Big-O 동일, 상수만 좋음
```

대부분의 코딩 테스트는 lazy로 충분. indexed heap은 운영에서 매우 큰 그래프나 dynamic graph에서 의미 있음.

### Q4. "Fibonacci heap은 뭐고 왜 안 쓰나?"

| | binary heap | Fibonacci heap |
|---|---|---|
| insert | O(log n) | O(1) amortized |
| extract-min | O(log n) | O(log n) amortized |
| decrease-key | O(log n) | **O(1) amortized** |
| merge | O(n) | **O(1)** |

이론적으로 Dijkstra O(E + V log V) — Big-O 개선. 하지만:
- 상수 매우 크고 구현 복잡.
- 캐시 비친화적 (포인터 자료구조).
- 실제 벤치에서 binary heap이 빠른 경우 다수.
- → 학술적으로만 의미, 실전엔 거의 안 씀. **pairing heap**이 실용적 대체.

### Q5. "스트리밍에서 메모리 제한이 있으면?"

- 정확한 K번째? — heap of size K로 O(K) 메모리.
- 정확한 quantile? — heap으로는 어려움. **t-digest**, **Greenwald-Khanna sketch**, **HDR histogram** 같은 sketch 자료구조.
- 정확한 median? — 모든 데이터를 봐야 정확함. 근사면 reservoir sampling + 정렬.

### Q6. "concurrent 환경에서?"

- `java.util.PriorityQueue`: thread-safe 아님.
- `java.util.concurrent.PriorityBlockingQueue`: ReentrantLock 기반, unbounded. blocking take/put 지원.
- `DelayQueue`: timestamp 기반, scheduled task용.
- 확장: `ScheduledThreadPoolExecutor` 내부도 PQ.

운영에서 "지연된 작업 재시도", "rate limiter" 구현에 자주 등장.

### Q7. "Heap sort는 왜 안 쓰나? 이론상 O(n log n)인데."

- **cache locality 나쁨**: sift-down은 멀리 떨어진 인덱스로 점프 → cache miss 폭증.
- **constants 큼**: quicksort/mergesort보다 비교/swap 수 많음.
- **not stable**: 같은 키의 상대 순서 보장 X.
- 장점: in-place + worst O(n log n) 보장 → **introsort** (quicksort + 깊이 한계 시 heap sort fallback)에 부분적으로 채택됨.

---

## 9. 다른 패턴과의 연결

### 9.1 Heap이 핵심인 알고리즘

| 알고리즘 | heap 역할 |
|---|---|
| **Dijkstra** | min-heap of (dist, node) — 가장 가까운 미방문 노드 추출 |
| **Prim's MST** | min-heap of edge weight |
| **Huffman coding** | min-heap of (freq, tree) — 빈도 낮은 둘 합치기 |
| **A\*** | min-heap of (f = g + h, node) |
| **K-way merge** | k 개의 min-heap pointer (23번) |
| **Top-K** | k 짜리 min/max-heap (215, 347) |
| **Median of stream** | two-heap (295) |
| **Event simulation** | min-heap of (time, event) — discrete event simulation |

### 9.2 라이브 코딩 패턴 매핑

- "정렬 + 가용 풀에서 최고/최소" → heap (IPO, 디스크 컨트롤러)
- "stream + Top K" → heap of size K
- "stream + median/quantile" → two-heap
- "greedy + 작은 것부터 합치기" → min-heap (Huffman, 카드 정렬)

### 9.3 운영 (시니어 마스터 관점) — heap이 production에서 어디 있나

**1. Log monitoring — Top-K errors**

```
실시간 로그 수집기 (Fluentd, Loki):
  매 1분 단위 윈도우에서 "가장 자주 발생한 에러 메시지 K개"
  → fingerprint 기반 카운터 + min-heap of size K
  → O(N log K) 메모리 O(K) — 초당 수십만 로그도 처리 가능

장애 대응 시 "지금 가장 시끄러운 에러부터" 우선 처리.
KSentinel/Sentry의 "Top Issues" 대시보드가 정확히 이 자료구조.
```

**2. Real-time leaderboard**

```
게임 점수 / e-commerce 인기 상품 / SNS trending:
  - Redis Sorted Set (skip list + hash) — heap의 운영 버전
  - 이론상 heap이지만 random access (rank 조회) + range query 위해 BBST 채택
  - ZADD/ZRANGEBYSCORE → O(log n) + 응답 O(k)
```

운영 코드에서 PriorityQueue를 직접 쓰는 일은 적지만, **이 자료구조를 골라 쓰는 사고**가 시니어의 핵심.

**3. K8s scheduler — pod priority queue**

```
kube-scheduler:
  - 펜딩 pod들을 priority 기반 heap에 보관
  - 가장 높은 priority pod부터 노드에 binding
  - preemption: 새 high-priority pod이 들어왔을 때 lower-priority pod evict
  → 정확히 PriorityQueue ADT
```

소스코드: `k8s.io/kubernetes/pkg/scheduler/internal/queue/scheduling_queue.go` — `PriorityQueue` 인터페이스 + heap 기반 구현.

**4. OS 프로세스 스케줄러**

```
Linux CFS는 red-black tree (BBST) 사용 — vruntime 기반 정렬.
BFS (Brain F\* Scheduler): O(1) priority queue.
realtime scheduler: priority 기반 multi-heap.
```

알고리즘 책의 heap이 그대로 커널에 박혀 있다.

**5. DB transaction scheduler / connection pool**

```
HikariCP, PgBouncer:
  - waiting connection request를 priority queue로 관리
  - timeout 짧은 것 우선 또는 FIFO
```

**6. Message broker — delayed queue / retry**

```
RabbitMQ, Kafka:
  - 재시도/지연 메시지는 timestamp 기반 priority queue
  - 만료 시각 도래하면 consume
  → Java DelayQueue, Redis ZADD with score=timestamp
```

**7. CDN / edge cache eviction**

```
LRU/LFU eviction:
  - LFU = min-heap of (access count, key)
  - 메모리 부족 시 root pop → 가장 덜 쓰인 항목 제거
```

**8. Event-driven simulation**

```
network simulator, queuing theory, game engine:
  - "다음 발생할 이벤트" = min-heap of (time, event)
  - poll → 가장 빠른 이벤트 처리 → 새 이벤트 push
  - 이게 discrete event simulation의 기본 데이터 구조
```

---

## 10. 백지에서 풀어보기 체크리스트

라이브 코딩 직전에 5분만 보면 좋을 자가 점검.

- [ ] heap의 두 불변식 (shape + order)을 그림 없이 말로 설명할 수 있다.
- [ ] sift-up/sift-down을 5x5 ASCII로 그릴 수 있다.
- [ ] build-heap이 O(n)인 이유를 한 줄로 답할 수 있다 ("leaf가 많고 leaf 비용 0, root는 비용 log n이지만 1개").
- [ ] Java `PriorityQueue`의 default가 min-heap임을 기억한다. max-heap은 `Comparator.reverseOrder()`.
- [ ] `b - a` overflow의 위험과 `Integer.compare(b, a)` 대안을 기억한다.
- [ ] Top K largest = **min-heap of size K** (반대 종류!).
- [ ] two-heap median의 불변식 (size 차 ≤ 1, lower.peek ≤ upper.peek)을 쓸 수 있다.
- [ ] K-way merge의 heap size는 N이 아니라 K임을 기억한다.
- [ ] heap iteration은 정렬 순서가 아니다.
- [ ] PriorityQueue는 thread-safe 아님 → `PriorityBlockingQueue`.
- [ ] indexed heap (decrease-key O(log n))이 Dijkstra에서 왜 좋은지 답할 수 있다.

---

## 11. 한 문장 요약

> **Heap = complete binary tree를 array에 펼친 자료구조. parent ≤/≥ children만 유지하면 (전체 정렬은 안 함) root에서 최솟값/최댓값을 O(1)에 얻을 수 있다. 코딩 테스트에서 "최소/최대를 반복 추출", "Top K", "K-way merge", "스트림의 중앙값"을 보면 30초 안에 heap을 후보로 올리고, Java/Kotlin 모두 `java.util.PriorityQueue`를 그대로 사용. 동률 처리·overflow·thread-safety만 챙기면 라이브 코딩 통과는 보장된다.**
