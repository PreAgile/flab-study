# 13. Greedy Algorithm (그리디)

> "지금 당장 가장 좋아 보이는 걸 고른다"는 입문자. 마스터는 **왜 지역 최적이 전역 최적인지 증명(exchange argument)** 을 먼저 확인하고, 증명 실패 시 즉시 DP로 전환한다.
>
> 그리디는 가장 위험한 패턴이다. 코드는 5줄로 짧지만, **반례 하나만 떠올리지 못해도 틀린다.** 면접관이 "왜 이게 옳은가?"를 물었을 때 "정렬하고 골랐다"로 끝나면 탈락이다. exchange argument 한 줄로 증명할 수 있어야 한다.

---

## 0. 인지 신호 — 그리디인지 30초 안에 판단

### 0.1 표면 키워드

| 신호 | 예시 표현 |
|---|---|
| **최대/최소** | "가능한 한 많은 활동을 선택", "최소 동전 개수" |
| **지금 즉시 선택** | "각 단계에서 한 번만 결정", "되돌릴 수 없음" |
| **정렬 후 sweep** | "정렬한 뒤 한 번 훑으면 답이 나옴" |
| **활동 선택 류** | end time이 빠른 것부터 / 작업 deadline / 회의실 배정 |
| **동전/거스름돈 류** | 표준 동전 (1,5,10,50,100,500) — 비표준이면 DP |
| **단속카메라/구명보트/큰 수 만들기** | 한국 코딩 테스트 단골 |

### 0.2 그리디가 통하는 구조적 조건 2가지

1. **Greedy Choice Property** — 매 단계의 지역 최적이 전역 최적의 일부가 된다.
2. **Optimal Substructure** — 한 번 선택하고 남은 문제도 동일 구조로 최적해를 가진다.

**둘 다 만족해야** 그리디가 옳다. 하나라도 빠지면 DP (12장)로 가야 한다.

### 0.3 그리디 vs DP 결정 트리

```
        문제에 "최대/최소"가 보임
                │
       선택의 순서가 정해져 있고
       이전 선택이 미래 선택을 제한?
                │
       ┌────────┴────────┐
       │                 │
     YES               NO
       │                 │
  exchange         완전 탐색 / Brute
  argument로        force부터 출발
  증명 시도?
       │
   ┌───┴───┐
   │       │
 성공     실패
   │       │
 Greedy   DP / Backtracking
```

핵심: **그리디 = "증명 가능한 지름길"**. 증명 못 하면 DP. 실제 면접에서 그리디로 시작했다가 반례 발견 → DP 전환은 흔한 패턴.

---

## 1. 백지 그리기 — 그리디 핵심 도식

### 1.1 Activity Selection — 가장 유명한 예제

```
[활동 5개, end time 순 정렬]

start: 1  3  0  5  3  5  6  8
end:   2  4  6  7  9  9  10 11

end time 기준 정렬 후:
      ┌──┐
      │A │ end=2
      └──┘
            ┌──┐
            │B │ end=4
            └──┘
   ┌─────────┐
   │   C     │ end=6  ← B와 겹침 → 버림
   └─────────┘
                ┌──┐
                │D │ end=7
                └──┘
                       ┌──┐
                       │E │ end=9
                       └──┘

선택: A(2) → B(4) → D(7) → E(9) = 4개
```

**왜 end time 순으로 정렬?** 가장 빨리 끝나는 활동을 고르면 **남은 시간이 최대화**된다 → 남은 문제(앞으로 고를 수 있는 활동 수)가 최대 → 전체 답도 최대. 이게 exchange argument.

### 1.2 Exchange Argument 도식 — 그리디 옳음 증명의 핵심

```
[가정] 최적해 OPT가 그리디 해 G와 다르다고 하자.

G:    [g1] [g2] [g3] ...
OPT:  [o1] [o2] [o3] ...

만약 g1 ≠ o1 이면:
  G는 가장 일찍 끝나는 것 g1을 골랐으므로 g1.end ≤ o1.end

OPT에서 o1을 g1으로 바꿔도:
  - g1.end ≤ o1.end 이므로 뒤에 오는 o2, o3, ...와 여전히 충돌 없음
  - 활동 수는 동일

→ "g1을 쓰는 또 다른 최적해"가 존재
→ 귀납적으로 G도 최적해

즉: 그리디 선택과 충돌하지 않는 최적해가 항상 존재한다.
```

이 한 페이지를 백지에서 그릴 수 있으면 면접관 질문 90%는 방어 가능.

### 1.3 그리디가 실패하는 반례 — 비표준 동전 시스템

```
[동전 = {1, 3, 4}, target = 6]

그리디 (큰 동전부터):
  6 = 4 + 1 + 1  → 3개

최적 (DP):
  6 = 3 + 3      → 2개

→ 그리디 실패. 4를 고른 순간 "3+3"의 가능성이 사라짐.
   greedy choice property가 깨졌다.
```

**한국 동전(1, 5, 10, 50, 100, 500)은 왜 통하는가?** matroid 이론 — 큰 단위가 작은 단위의 배수 + 충분한 간격 → exchange argument 성립. 비표준이면 무조건 DP.

### 1.4 세 가지 그리디 접근법

```
┌─────────────────────────────────────────────────────────┐
│ A. 정렬 + Sweep                                          │
│    - 활동 선택, 회의실 배정, 단속카메라                  │
│    - O(N log N) — 정렬이 지배                            │
│                                                          │
│ B. Priority Queue (Heap) 기반                            │
│    - Huffman 코드, Dijkstra, K개 작업 스케줄             │
│    - "다음에 가장 좋은 것"을 동적으로 뽑을 때            │
│    - O(N log N)                                          │
│                                                          │
│ C. 두 포인터 + Greedy                                    │
│    - 구명보트, Container With Most Water                 │
│    - 정렬 후 양 끝에서 좁히며 즉시 결정                  │
│    - O(N log N) (정렬) or O(N) (이미 정렬)               │
└─────────────────────────────────────────────────────────┘
```

---

## 2. 직관과 정의

### 2.1 한 줄 비유

> "산을 오를 때 매 순간 가장 가파른 방향만 본다. 단, 그 산이 봉우리 하나뿐(unimodal)임이 보장될 때만."

봉우리가 여럿이면(다중 극대) 그리디는 지역 최적에서 멈춘다 — 이게 NP-hard 문제에서 그리디가 근사해(approximation)로만 쓰이는 이유.

### 2.2 정확한 정의

**Greedy Algorithm**: 매 단계에서 현재까지의 정보만으로 **되돌릴 수 없는 결정**을 내려, 전체 해를 구성하는 알고리즘. 다음 두 성질이 보장될 때만 정답.

1. **Greedy Choice Property**: 지역 최적 선택이 전역 최적해에 포함됨이 증명됨.
2. **Optimal Substructure**: 부분 문제의 최적해가 전체 최적해의 일부.

### 2.3 그리디 증명 기법 3가지

| 기법 | 핵심 | 대표 예 |
|---|---|---|
| **Exchange Argument** | OPT의 첫 선택을 그리디 선택으로 바꿔도 여전히 OPT임을 보임 | Activity Selection, Huffman |
| **Greedy Stays Ahead** | k번째 단계까지 그리디가 OPT보다 항상 같거나 앞서감을 귀납 증명 | Job Scheduling with Deadlines |
| **Matroid 이론** | 문제가 matroid 구조면 그리디가 항상 옳음 (Edmonds) | MST (Kruskal), 최대 가중치 독립 집합 |

면접에서는 **Exchange Argument 한 줄**이면 충분하다. matroid는 박사 면접용.

### 2.4 그리디 vs DP — 구체적 선택 기준

| 항목 | Greedy | DP |
|---|---|---|
| 선택 후 되돌리기 | 안 함 | 모든 가능성 시도 |
| 시간 복잡도 | 보통 O(N log N) | O(N²), O(N·K) 등 |
| 공간 복잡도 | O(1) ~ O(N) | O(N) ~ O(N²) |
| 증명 난이도 | 어려움 (exchange argument 필요) | 비교적 쉬움 (재귀식만 세우면) |
| 실패 모드 | 반례 한 개로 무너짐 | 점화식 틀려도 작은 입력으로 검증 가능 |
| 면접 안전성 | 위험 (증명 못 하면 0점) | 안전 (메모이제이션은 항상 정답) |

**실전 팁**: 면접에서 그리디가 보이면 **반례 1~2개를 먼저 떠올려본다.** 반례가 안 떠오르고 exchange argument가 떠오르면 그리디. 둘 다 막히면 DP.

---

## 3. Java 템플릿

### 3.1 정렬 + Sweep 템플릿 (가장 흔함)

```java
public int activitySelection(int[][] intervals) {
    if (intervals == null || intervals.length == 0) return 0;

    // 1. end time 기준 오름차순 정렬
    Arrays.sort(intervals, (a, b) -> Integer.compare(a[1], b[1]));

    int count = 1;
    int lastEnd = intervals[0][1];

    // 2. 한 번 sweep — 겹치지 않으면 선택
    for (int i = 1; i < intervals.length; i++) {
        if (intervals[i][0] >= lastEnd) {  // start ≥ 이전 end
            count++;
            lastEnd = intervals[i][1];
        }
    }
    return count;
}
```

**핵심 포인트**:
- `Integer.compare`로 정렬 (오버플로우 안전 — `a[1] - b[1]`은 음수+양수에서 터짐)
- 비교 키 선택이 그리디의 본질 — start vs end 잘못 고르면 반례 등장
- `>=`인지 `>`인지 — 끝점과 시작점이 같을 때 겹침으로 볼지 (문제마다 다름)

### 3.2 Priority Queue + Greedy 템플릿

```java
public int kthLargest(int[] nums, int k) {
    // min-heap 크기 k 유지 — top이 곧 k번째 큰 수
    PriorityQueue<Integer> pq = new PriorityQueue<>();
    for (int n : nums) {
        pq.offer(n);
        if (pq.size() > k) pq.poll();
    }
    return pq.peek();
}

// 회의실 배정 (LeetCode 253) — 진행 중 회의 end time 최소 추적
public int minMeetingRooms(int[][] intervals) {
    Arrays.sort(intervals, (a, b) -> a[0] - b[0]);  // start 기준
    PriorityQueue<Integer> pq = new PriorityQueue<>();  // end times

    for (int[] iv : intervals) {
        if (!pq.isEmpty() && pq.peek() <= iv[0]) {
            pq.poll();  // 끝난 회의 방 재활용
        }
        pq.offer(iv[1]);
    }
    return pq.size();
}
```

### 3.3 두 포인터 + Greedy 템플릿

```java
public int boatRescue(int[] people, int limit) {
    Arrays.sort(people);
    int left = 0, right = people.length - 1;
    int boats = 0;

    while (left <= right) {
        if (people[left] + people[right] <= limit) {
            left++;  // 가벼운 사람도 함께
        }
        right--;     // 무거운 사람은 무조건 보트 1개
        boats++;
    }
    return boats;
}
```

**왜 옳은가?** 가장 무거운 사람은 어떻게든 보트 1대 차지. 그와 함께 태울 수 있는 가장 가벼운 사람을 같이 태우는 게 손해가 아님 — 가벼운 사람을 따로 태우려 해도 결국 보트 1대 필요.

---

## 4. Kotlin 템플릿

### 4.1 정렬 + Sweep

```kotlin
fun activitySelection(intervals: Array<IntArray>): Int {
    if (intervals.isEmpty()) return 0

    intervals.sortBy { it[1] }  // end time 기준

    var count = 1
    var lastEnd = intervals[0][1]

    for (i in 1 until intervals.size) {
        if (intervals[i][0] >= lastEnd) {
            count++
            lastEnd = intervals[i][1]
        }
    }
    return count
}
```

### 4.2 Priority Queue + Greedy

```kotlin
import java.util.PriorityQueue

fun minMeetingRooms(intervals: Array<IntArray>): Int {
    intervals.sortBy { it[0] }
    val pq = PriorityQueue<Int>()

    for (iv in intervals) {
        if (pq.isNotEmpty() && pq.peek() <= iv[0]) {
            pq.poll()
        }
        pq.offer(iv[1])
    }
    return pq.size
}
```

### 4.3 두 포인터 + Greedy

```kotlin
fun boatRescue(people: IntArray, limit: Int): Int {
    people.sort()
    var left = 0
    var right = people.size - 1
    var boats = 0

    while (left <= right) {
        if (people[left] + people[right] <= limit) left++
        right--
        boats++
    }
    return boats
}
```

### 4.4 Kotlin 관용 표현 — Comparator 체이닝

```kotlin
// 큰 수 만들기 / 단속카메라처럼 복합 키 정렬
intervals.sortedWith(compareBy({ it[1] }, { it[0] }))

// 내림차순 + 보조 키
items.sortedWith(compareByDescending<Item> { it.value }.thenBy { it.weight })
```

`compareBy { it.x }`는 자연 정렬 — 음수 빼기 트릭 같은 오버플로우 위험이 없고, 가독성도 우월.

---

## 5. 시간/공간 복잡도

| 변형 | 시간 | 공간 | 비고 |
|---|---|---|---|
| 정렬 + sweep | O(N log N) | O(1) or O(log N) (정렬 stack) | 정렬이 지배 |
| Priority Queue 기반 | O(N log N) | O(N) (heap) | poll/offer log N |
| 두 포인터 + greedy | O(N log N) (정렬) → O(N) | O(1) | 정렬 후 단일 패스 |
| 이미 정렬된 입력 | O(N) | O(1) | 최선 |

**왜 거의 항상 O(N log N)?** 그리디는 보통 "어떤 키 기준 정렬 + 한 번 훑기"이고, 정렬 비용 O(N log N)이 지배한다. counting sort 같은 비교 없는 정렬을 쓸 수 있으면 O(N)으로 떨어진다 (값 범위가 작을 때).

---

## 6. 대표 문제

### 6.1 LeetCode 55. Jump Game

**요약**: `nums[i]`만큼 최대 점프 가능. 마지막 칸까지 도달 가능한가?

**왜 그리디?** "지금까지 도달 가능한 최대 인덱스"만 추적하면 됨 — 그게 현재 위치보다 작아지는 순간 실패. **Greedy Stays Ahead** 증명.

**증명 스케치**: i번째 칸에서의 최대 도달 = `max(이전 최대, i + nums[i])`. 어떤 j ≤ 최대도달 인덱스라면 j까지 가는 경로가 반드시 존재(귀납). 따라서 전역 최대 도달이 n-1 이상이면 OK.

**Java**:
```java
public boolean canJump(int[] nums) {
    int maxReach = 0;
    for (int i = 0; i < nums.length; i++) {
        if (i > maxReach) return false;     // 도달 불가
        maxReach = Math.max(maxReach, i + nums[i]);
        if (maxReach >= nums.length - 1) return true;
    }
    return true;
}
```

**Kotlin**:
```kotlin
fun canJump(nums: IntArray): Boolean {
    var maxReach = 0
    for (i in nums.indices) {
        if (i > maxReach) return false
        maxReach = maxOf(maxReach, i + nums[i])
        if (maxReach >= nums.size - 1) return true
    }
    return true
}
```

**복잡도**: 시간 O(N), 공간 O(1).

**함정**:
- `nums = [0]`: 이미 도착. true.
- `i > maxReach`는 진행 불가 신호 — 이걸 빠뜨리면 무한 반복은 아니지만 잘못된 true.

---

### 6.2 LeetCode 45. Jump Game II

**요약**: 마지막 칸까지 가는 **최소 점프 수**.

**왜 그리디?** BFS 레벨처럼 생각 — 현재 도달 가능한 구간 `[currentEnd]`을 모두 탐색한 후, 그 구간 내에서 갈 수 있는 최대 인덱스로 점프. **각 점프는 다음 구간의 최대 도달점**을 선택 = 지역 최적이 전역 최적.

**증명 스케치**: k번 점프 후 도달 가능한 최대 인덱스 = `f(k)`. 그리디는 매번 `f(k)`를 최대화 → 더 큰 `f(k+1)` → 같은 점프 수로 가장 멀리.

```
[nums = 2,3,1,1,4]

idx:    0  1  2  3  4
nums:   2  3  1  1  4
        ▲           ▲
        start       end

점프 1: [0] → 도달 가능 [1,2]. 그 중 최대 도달 = max(1+3, 2+1) = 4
점프 2: 4 ≥ n-1 → 도착!  답 = 2
```

**Java**:
```java
public int jump(int[] nums) {
    int jumps = 0, currentEnd = 0, farthest = 0;
    for (int i = 0; i < nums.length - 1; i++) {
        farthest = Math.max(farthest, i + nums[i]);
        if (i == currentEnd) {  // 현재 구간 끝 도달 → 점프 필요
            jumps++;
            currentEnd = farthest;
            if (currentEnd >= nums.length - 1) break;
        }
    }
    return jumps;
}
```

**Kotlin**:
```kotlin
fun jump(nums: IntArray): Int {
    var jumps = 0
    var currentEnd = 0
    var farthest = 0
    for (i in 0 until nums.size - 1) {
        farthest = maxOf(farthest, i + nums[i])
        if (i == currentEnd) {
            jumps++
            currentEnd = farthest
            if (currentEnd >= nums.size - 1) break
        }
    }
    return jumps
}
```

**복잡도**: 시간 O(N), 공간 O(1).

**함정**:
- 마지막 인덱스에서 점프 카운트하면 +1 더해짐 → `i < nums.length - 1`.
- BFS로 풀어도 정답이지만 O(N²) — 그리디가 압도적.

---

### 6.3 LeetCode 134. Gas Station

**요약**: 원형 도로에 주유소 N개. `gas[i]` 충전, `cost[i]` 다음으로 이동 비용. 한 바퀴 돌 수 있는 시작점 인덱스. 없으면 -1.

**왜 그리디?** 두 가지 직관.
1. **존재성**: `sum(gas) ≥ sum(cost)` ↔ 해 존재.
2. **위치**: 시작점 `s`에서 출발해 `i`에서 누적 연료 < 0이면, `s ~ i` 어떤 점에서 시작해도 실패 → **다음 후보는 `i+1`**.

**증명 스케치** (Exchange Argument 변형):
- `s`에서 출발해 `i`에서 처음 음수 → `s+1, s+2, ..., i`에서 출발해도 `i`까지 모자람 (출발 시 +0이라 누적이 더 작거나 같음).
- 따라서 `i+1`이 다음 유일한 후보.
- 전체 합 ≥ 0이면 이 후보가 정답임이 보장됨.

```
[gas  = 1,2,3,4,5]
[cost = 3,4,5,1,2]

i:        0   1   2   3   4
diff:    -2  -2  -2  +3  +3
tank:    -2  -4  -6  -3   0   ← s=0 시작 시 i=0에서 이미 음수
                              → s=3부터 다시 시도

s=3:      tank=3 → 3+3=6 → 6-2+(1-3)=... = 한 바퀴 성공
답: 3
```

**Java**:
```java
public int canCompleteCircuit(int[] gas, int[] cost) {
    int total = 0, tank = 0, start = 0;
    for (int i = 0; i < gas.length; i++) {
        int diff = gas[i] - cost[i];
        total += diff;
        tank += diff;
        if (tank < 0) {           // 여기까지 못 옴 → 다음에서 재시작
            start = i + 1;
            tank = 0;
        }
    }
    return total >= 0 ? start : -1;
}
```

**Kotlin**:
```kotlin
fun canCompleteCircuit(gas: IntArray, cost: IntArray): Int {
    var total = 0
    var tank = 0
    var start = 0
    for (i in gas.indices) {
        val diff = gas[i] - cost[i]
        total += diff
        tank += diff
        if (tank < 0) {
            start = i + 1
            tank = 0
        }
    }
    return if (total >= 0) start else -1
}
```

**복잡도**: 시간 O(N), 공간 O(1). Brute force는 O(N²).

**함정**:
- `start = i + 1`이 `n` 넘어가면 -1이 아닌 0으로 wrap이 아니라 그냥 -1 처리됨 (total < 0이라). 정확.
- `tank < 0` 체크를 `<=`로 하면 0인 경계에서 시작점이 뒤로 밀려 틀림.

---

### 6.4 LeetCode 763. Partition Labels

**요약**: 문자열을 가능한 한 많은 부분으로 나누되, 각 문자가 단 하나의 부분에만 등장. 각 부분 길이 반환.

**왜 그리디?** 각 문자의 **마지막 등장 위치**를 미리 구해두고, 한 번 sweep. 현재 부분의 끝 = `max(이미 본 문자들의 last index)`. `i == end`가 되면 분리.

**증명 스케치**: 부분을 더 잘게 자르려면 어떤 문자가 두 부분에 걸쳐야 함 → 조건 위반. 따라서 그리디가 만든 분할이 최대 개수.

```
s = "ababcbacadefegdehijhklij"

last index:
  a:8, b:5, c:7, d:14, e:15, f:11, g:13, h:19, i:22, j:23, k:20, l:21

i=0: 'a', end = max(0,8) = 8
i=1: 'b', end = max(8,5) = 8
...
i=8: 'a', end = 8 → i==end → 분리! 길이 9 ("ababcbaca")
i=9: 'd', end = 14
...
i=15: 'e', end = 15 → 분리! 길이 7 ("defegde")
...

답: [9, 7, 8]
```

**Java**:
```java
public List<Integer> partitionLabels(String s) {
    int[] last = new int[26];
    for (int i = 0; i < s.length(); i++) last[s.charAt(i) - 'a'] = i;

    List<Integer> result = new ArrayList<>();
    int start = 0, end = 0;
    for (int i = 0; i < s.length(); i++) {
        end = Math.max(end, last[s.charAt(i) - 'a']);
        if (i == end) {
            result.add(end - start + 1);
            start = i + 1;
        }
    }
    return result;
}
```

**Kotlin**:
```kotlin
fun partitionLabels(s: String): List<Int> {
    val last = IntArray(26)
    for (i in s.indices) last[s[i] - 'a'] = i

    val result = mutableListOf<Int>()
    var start = 0
    var end = 0
    for (i in s.indices) {
        end = maxOf(end, last[s[i] - 'a'])
        if (i == end) {
            result.add(end - start + 1)
            start = i + 1
        }
    }
    return result
}
```

**복잡도**: 시간 O(N), 공간 O(1) (26 알파벳).

**함정**:
- 알파벳이 아닌 일반 문자라면 `HashMap<Character,Integer>` 사용 — 공간 O(K).
- `start`를 갱신하는 걸 빼먹으면 길이가 누적되어 틀림.

---

### 6.5 LeetCode 121 & 122. Best Time to Buy and Sell Stock (I, II)

#### 121 (한 번만 매수/매도)

**요약**: 한 번만 사고 한 번 팔아 최대 이익.

**왜 그리디?** 각 날에 대해 "지금까지 본 최저가에 샀다면 오늘 팔 때 이익"을 계산 — 모든 i에 대해 한 번 sweep으로 최대 이익. 미래의 최저가는 알 수 없지만 **과거 최저가는 단조** → 그리디.

**Java**:
```java
public int maxProfit(int[] prices) {
    int minPrice = Integer.MAX_VALUE;
    int maxProfit = 0;
    for (int p : prices) {
        if (p < minPrice) minPrice = p;
        else if (p - minPrice > maxProfit) maxProfit = p - minPrice;
    }
    return maxProfit;
}
```

**Kotlin**:
```kotlin
fun maxProfit(prices: IntArray): Int {
    var minPrice = Int.MAX_VALUE
    var maxProfit = 0
    for (p in prices) {
        if (p < minPrice) minPrice = p
        else if (p - minPrice > maxProfit) maxProfit = p - minPrice
    }
    return maxProfit
}
```

#### 122 (여러 번 매수/매도 허용, 한 번에 1주만 보유)

**요약**: 매일 사고팔기 가능. 최대 누적 이익.

**왜 그리디?** **모든 상승 구간의 합 = 최대 이익**. 증명 — 어떤 구간 [i, j] 매수/매도는 일별 차분의 합과 동일: `p[j] - p[i] = (p[i+1]-p[i]) + (p[i+2]-p[i+1]) + ... + (p[j]-p[j-1])`. 따라서 양수인 차분만 모두 더하면 최대.

```
prices = [7,1,5,3,6,4]

diff:    -6, +4, -2, +3, -2
양수만:       +4,     +3       → 합 7

[1→5: 4 이익] + [3→6: 3 이익] = 7
```

**Java**:
```java
public int maxProfitII(int[] prices) {
    int profit = 0;
    for (int i = 1; i < prices.length; i++) {
        if (prices[i] > prices[i-1]) {
            profit += prices[i] - prices[i-1];
        }
    }
    return profit;
}
```

**Kotlin**:
```kotlin
fun maxProfitII(prices: IntArray): Int {
    var profit = 0
    for (i in 1 until prices.size) {
        if (prices[i] > prices[i-1]) profit += prices[i] - prices[i-1]
    }
    return profit
}
```

**복잡도**: 시간 O(N), 공간 O(1).

**함정**:
- 121에서 매도 후 다시 매수 불가 — minPrice가 단조 감소만 가능한 게 핵심.
- 122에서 "수수료가 있다면?" 꼬리질문 — 그러면 DP로 전환 (LeetCode 714).

---

### 6.6 LeetCode 435. Non-overlapping Intervals

**요약**: 최소 몇 개를 제거해야 모든 구간이 안 겹치는가?

**왜 그리디?** 전체 N에서 **최대 비겹침 구간 수**를 빼면 답. 최대 비겹침 = Activity Selection. **end time 기준 정렬** 후 sweep.

**증명** (Exchange Argument):
- 최적해의 첫 번째 구간을 `o1`, 그리디의 첫 번째를 `g1`이라 하자.
- 그리디는 end가 가장 빠른 것 → `g1.end ≤ o1.end`.
- 최적해의 `o1`을 `g1`으로 바꿔도 뒤의 구간들과 충돌 없음 — `g1.end ≤ o1.end`이므로.
- 귀납 → 그리디 = 최적.

**Java**:
```java
public int eraseOverlapIntervals(int[][] intervals) {
    if (intervals.length == 0) return 0;
    Arrays.sort(intervals, (a, b) -> Integer.compare(a[1], b[1]));

    int keep = 1;
    int lastEnd = intervals[0][1];
    for (int i = 1; i < intervals.length; i++) {
        if (intervals[i][0] >= lastEnd) {
            keep++;
            lastEnd = intervals[i][1];
        }
    }
    return intervals.length - keep;
}
```

**Kotlin**:
```kotlin
fun eraseOverlapIntervals(intervals: Array<IntArray>): Int {
    if (intervals.isEmpty()) return 0
    intervals.sortBy { it[1] }

    var keep = 1
    var lastEnd = intervals[0][1]
    for (i in 1 until intervals.size) {
        if (intervals[i][0] >= lastEnd) {
            keep++
            lastEnd = intervals[i][1]
        }
    }
    return intervals.size - keep
}
```

**복잡도**: 시간 O(N log N), 공간 O(1).

**함정**:
- **start time 기준으로 정렬하면 틀림** — 큰 구간 하나가 작은 구간 여러 개를 가린다.
- 끝점=시작점이 겹침으로 간주되는지 (`>=` vs `>`)는 문제마다 다름. LeetCode 435는 `[1,2], [2,3]` 비겹침 → `>=`.

---

### 6.7 프로그래머스 — 큰 수 만들기

**요약**: 숫자 문자열에서 k개를 제거해 가장 큰 수.

**왜 그리디?** **monotonic stack** + greedy — 스택에 쌓아가다가, 직전 숫자가 현재 숫자보다 작고 k가 남았으면 pop. 가장 앞자리부터 큰 숫자를 만들어야 전체 수가 커진다.

**증명** (Exchange Argument):
- 어떤 자리 i에서 그리디가 `d`를 선택, 최적해가 `d' < d`를 선택했다 가정.
- 같은 자리 i에서 `d` > `d'`이므로 그리디 답이 더 큼 → 모순.

```
"1924" k=2

stack: [1]
'9' > 1 → pop 1 (k=1), push 9.  stack: [9]
'2' < 9 → push 2.                stack: [9,2]
'4' > 2 → pop 2 (k=0), push 4.   stack: [9,4]

남은 k=0. 답: "94"
```

**Java**:
```java
public String solution(String number, int k) {
    StringBuilder stack = new StringBuilder();
    for (char c : number.toCharArray()) {
        while (k > 0 && stack.length() > 0 && stack.charAt(stack.length()-1) < c) {
            stack.deleteCharAt(stack.length()-1);
            k--;
        }
        stack.append(c);
    }
    // k가 남았으면 뒤에서 잘라냄 (이미 단조 감소 상태)
    stack.setLength(stack.length() - k);
    return stack.toString();
}
```

**Kotlin**:
```kotlin
fun solution(number: String, k: Int): String {
    val stack = StringBuilder()
    var remain = k
    for (c in number) {
        while (remain > 0 && stack.isNotEmpty() && stack.last() < c) {
            stack.deleteCharAt(stack.length - 1)
            remain--
        }
        stack.append(c)
    }
    stack.setLength(stack.length - remain)
    return stack.toString()
}
```

**복잡도**: 시간 O(N), 공간 O(N). 각 문자는 최대 1번 push, 1번 pop.

**함정**:
- 끝까지 갔는데 k가 남으면 (`"4321" k=2`) 뒤에서 잘라야 함.
- LeetCode 402 Remove K Digits는 동일 패턴 — 단, 가장 작은 수를 만들기 → 부등호 반전 (`>`).

---

### 6.8 프로그래머스 — 구명보트

**요약**: 사람들 무게, 보트 최대 2명 + 무게 한도. 최소 보트 수.

**왜 그리디?** 가장 무거운 사람 + 가장 가벼운 사람 페어링. 가벼운 사람을 따로 태우는 게 손해가 아님 — 무거운 사람은 어차피 보트 1대 차지하니까.

**증명** (Exchange Argument):
- 최적해가 가장 무거운 사람 H를 다른 사람 X(≠ 가장 가벼운 L)와 페어했다 가정.
- L도 어딘가 다른 사람 Y와 페어 또는 혼자.
- H와 L을 swap → H+L도 limit 이내이고 (L ≤ X이므로), X+Y가 가능했으면 X와 Y만 단독으로 보트.
- 보트 수 동일 또는 감소 → 그리디 = 최적.

**Java**:
```java
public int solution(int[] people, int limit) {
    Arrays.sort(people);
    int left = 0, right = people.length - 1;
    int boats = 0;
    while (left <= right) {
        if (people[left] + people[right] <= limit) left++;
        right--;
        boats++;
    }
    return boats;
}
```

**Kotlin**:
```kotlin
fun solution(people: IntArray, limit: Int): Int {
    people.sort()
    var left = 0
    var right = people.size - 1
    var boats = 0
    while (left <= right) {
        if (people[left] + people[right] <= limit) left++
        right--
        boats++
    }
    return boats
}
```

**복잡도**: 시간 O(N log N), 공간 O(1).

**함정**:
- 한 명이 limit 초과? 문제 제약상 보장됨. 안 보장되면 별도 처리.
- `left == right` 케이스 — 본인 혼자 보트 1대.

---

### 6.9 프로그래머스 — 단속카메라

**요약**: 차량 진입~진출 구간이 주어짐. 모든 차량이 최소 1번 카메라에 찍히도록 카메라 최소 개수.

**왜 그리디?** **end time(진출 지점) 기준 정렬** 후, 가장 빠른 진출 지점에 카메라 배치 → 그 카메라가 커버 못 하는 다음 차량에 또 배치. Activity Selection의 쌍대 문제.

**증명** (Exchange Argument):
- 가장 빨리 나가는 차의 진출 지점 e₁에 카메라를 두면 e₁ ≤ 어떤 차의 진출 지점이라도 그 차가 e₁에서 아직 도로 위에 있을 가능성이 최대 → 한 카메라로 최대한 많이 커버.
- 다른 위치에 두면 동일 카메라로 덜 커버 → 더 많은 카메라 필요.

```
[차량들, end 기준 정렬]
[-20, -15]  → 카메라 -15
[-14, -5]   → -15 ≥ -14? No (route는 진입~진출). -15 > -5? 아니. 카메라 위치 -15가 [-14,-5] 안에 있나? -15 < -14 → 안 들어감 → 새 카메라 -5
[-18, -13]  → -15 ∈ [-18,-13] → 커버됨
[-5, -3]    → -5 ∈ [-5,-3] → 커버됨

답: 2
```

**Java**:
```java
public int solution(int[][] routes) {
    Arrays.sort(routes, (a, b) -> Integer.compare(a[1], b[1]));
    int cameras = 0;
    int lastCamera = Integer.MIN_VALUE;
    for (int[] r : routes) {
        if (r[0] > lastCamera) {  // 이전 카메라로 커버 안 됨
            cameras++;
            lastCamera = r[1];    // 진출 지점에 새 카메라
        }
    }
    return cameras;
}
```

**Kotlin**:
```kotlin
fun solution(routes: Array<IntArray>): Int {
    routes.sortBy { it[1] }
    var cameras = 0
    var lastCamera = Int.MIN_VALUE
    for (r in routes) {
        if (r[0] > lastCamera) {
            cameras++
            lastCamera = r[1]
        }
    }
    return cameras
}
```

**복잡도**: 시간 O(N log N), 공간 O(1).

**함정**:
- **start 기준 정렬하면 틀림** — 활동 선택 류는 항상 end 기준.
- `r[0] > lastCamera` 가 `>=`이면 진입점=카메라 위치 케이스에서 커버로 인정 안 됨 → 카메라 1개 더. 문제 정의 확인 필수.

---

### 6.10 프로그래머스 — 조이스틱

**요약**: 알파벳 조이스틱. 위/아래(A↔Z 알파벳 변경) + 좌/우(커서 이동). 목표 문자열까지 최소 조작 수.

**왜 그리디?** 두 단계로 분리.
1. **알파벳 변경 비용**: 각 자리 `min(c - 'A', 'Z' - c + 1)` 합 (시계/반시계 짧은 쪽).
2. **커서 이동 비용**: 'A'가 아닌 자리들을 모두 방문하는 최단 경로 — 양방향 + 반대 방향 시도 포함. 그리디로 각 시작점에서 좌/우 사이드의 'A' 연속 구간 길이를 빼는 방식.

```
"BBAAAAAB" (길이 8)

알파벳 변경: B=1, B=1, A=0, ..., A=0, B=1 → 3

커서 이동:
  - 단순 오른쪽으로만: 7회
  - 오른쪽 1칸 + 왼쪽 1칸 (마지막 B로): 1 + 1 = 2회 ← 그리디 선택
  - 더 효율적인 경우 비교

답: 3 + 2 = 5
```

**Java**:
```java
public int solution(String name) {
    int n = name.length();
    int change = 0;
    for (char c : name.toCharArray()) {
        change += Math.min(c - 'A', 'Z' - c + 1);
    }

    int move = n - 1;  // 기본: 끝까지 오른쪽
    for (int i = 0; i < n; i++) {
        int next = i + 1;
        while (next < n && name.charAt(next) == 'A') next++;
        // i까지 오른쪽 → 다시 왼쪽 → 끝에서 next로 또는 반대
        move = Math.min(move, i * 2 + (n - next));
        move = Math.min(move, (n - next) * 2 + i);
    }
    return change + move;
}
```

**Kotlin**:
```kotlin
fun solution(name: String): Int {
    val n = name.length
    var change = 0
    for (c in name) change += minOf(c - 'A', 'Z' - c + 1)

    var move = n - 1
    for (i in 0 until n) {
        var next = i + 1
        while (next < n && name[next] == 'A') next++
        move = minOf(move, i * 2 + (n - next))
        move = minOf(move, (n - next) * 2 + i)
    }
    return change + move
}
```

**복잡도**: 시간 O(N²) (while 누적 N), 공간 O(1).

**함정**:
- 모든 문자가 'A'인 경우 → next = n, move = 0이어야 함.
- 그리디의 한계 — 일반적으로 TSP는 NP-hard. 이 문제는 1D + 양방향이라 그리디가 통하지만, 복잡한 변형에서는 DP/BFS 필요.

---

## 7. 함정·엣지케이스

### 7.1 그리디가 실패하는 패턴

| 상황 | 왜 실패? | 대안 |
|---|---|---|
| 비표준 동전 시스템 ({1,3,4}) | greedy choice property 위반 | DP (Knapsack류) |
| 0/1 Knapsack | 부분 선택 불가 → exchange argument 안 통함 | DP |
| 일반 TSP | 지역 최적 != 전역 (NP-hard) | DP O(N²·2^N) or Approximation |
| 동전 한 종류씩만 사용 가능 (가짓수 제약) | 선택 후 상태가 단순 합 아님 | DP |

### 7.2 정렬 키 선택 실수

```
[Activity Selection — start 기준 정렬]
[1,10] [2,3] [4,5]

start 정렬: [1,10] [2,3] [4,5]
greedy:     [1,10] 선택 → [2,3], [4,5] 둘 다 충돌
결과: 1개

[Activity Selection — end 기준 정렬]
end 정렬:   [2,3] [4,5] [1,10]
greedy:     [2,3] → [4,5] 선택 (1,10은 충돌)
결과: 2개 ← 정답
```

→ Activity Selection 류는 **항상 end 기준**. 면접에서 start로 시작했다가 반례로 깨진다면 즉시 인정하고 end로 전환.

### 7.3 동률(tie) 처리

```kotlin
// 종료 시점이 같으면 어느 걸 먼저?
intervals.sortedWith(compareBy({ it[1] }, { it[0] }))
//                              주키        보조키

// 예: [1,5] vs [2,5] — 어느 게 먼저?
// Activity Selection: 둘 다 동일 효과 (다음 선택은 start ≥ 5인 것)
// 단속카메라: 차이 없음
// 다른 문제: 보조 키로 start asc/desc가 답을 가르기도 함
```

면접에서 **"동률 처리를 어떻게?"** 라는 질문은 합격 신호 — 보조 키의 영향을 분석할 수 있는지 본다.

### 7.4 Comparator 오버플로우

```java
// ❌ 음수 - 양수 = overflow
Arrays.sort(arr, (a, b) -> a[1] - b[1]);

// ✅ 항상 안전
Arrays.sort(arr, (a, b) -> Integer.compare(a[1], b[1]));
```

`Integer.MIN_VALUE - 1` 같은 케이스에서 `a-b`는 양수가 되어 비교가 뒤집힘. 코딩 테스트에서 시간 잡아먹는 흔한 버그.

### 7.5 빈 입력 / 단일 원소

```java
if (intervals == null || intervals.length == 0) return 0;
if (intervals.length == 1) return 1;
```

`intervals[0]` 접근 전 size 체크. NPE/IndexOutOfBounds로 0점 받는 케이스 빈출.

### 7.6 누적 변수 초기값

| 변수 | 초기값 | 함정 |
|---|---|---|
| minPrice | `Integer.MAX_VALUE` | 0으로 두면 매수가 0원으로 잘못 계산 |
| maxReach | `0` (인덱스) | -1로 두면 첫 인덱스 0이 도달 불가로 |
| lastCamera | `Integer.MIN_VALUE` | 0으로 두면 음수 좌표 시 오작동 |
| lastEnd | `intervals[0][1]` 또는 `Integer.MIN_VALUE` | 0이면 음수 시작 구간 문제 |

음수 좌표 가능성을 항상 의심 — `Integer.MIN_VALUE` 또는 `Long.MIN_VALUE` 사용.

---

## 8. 꼬리질문 트리

```
면접관: "이 문제 풀어보세요"
                │
당신: "그리디로 풀겠습니다. end 기준 정렬 후..."
                │
       ┌────────┴────────┐
       │                 │
"왜 그리디인가요?"   "DP로도 가능?"
       │                 │
[Exchange Argument]   [O(N²) 가능하지만 그리디가
"end가 빠른 것을      O(N log N)로 더 빠름.
선택하면 남은 시간이  단, 제약(예: cooldown)이
최대 → 남은 부분 문제 추가되면 DP로 전환 필요"
가 최대 → 전역 최대"
       │                 │
"증명 더 자세히?"    "근사 알고리즘?"
       │                 │
[OPT의 첫 선택을      [그리디는 TSP/Set Cover
g1으로 swap해도       같은 NP-hard 문제에서
OPT 유지됨.           Approximation ratio
귀납적으로 그리디 OK] log N 등으로 쓰임.
                      예: 2-approximation
                      vertex cover]
       │
"반례 없나요?"
       │
[있다면 그리디 X.
이 문제는 matroid
구조 또는 exchange
argument로 증명됨]
```

### 8.1 자주 나오는 후속 질문

| 질문 | 답 |
|---|---|
| "더 빠르게 가능?" | 정렬 O(N log N)이 lower bound. 정수 + 좁은 범위면 counting sort로 O(N). |
| "메모리 줄이려면?" | 정렬을 in-place로. 결과를 누적 변수만 유지. |
| "스트리밍 (전체 입력 못 봄)이면?" | 그리디 안 됨 — 미래 정보 필요. Online 알고리즘 / Competitive ratio 분석. |
| "Approximation으로 그리디?" | Set Cover ln(N), Vertex Cover 2-approx, TSP MST 2-approx. |
| "병렬화?" | 정렬은 병렬 가능 (parallel sort). Sweep은 본질적으로 순차 — 다른 알고리즘 필요. |
| "왜 DP 안 쓰고 그리디?" | "Exchange argument로 정확성 증명됨 + O(N log N)이라 O(N²) DP보다 빠름." |

### 8.2 그리디 증명 4단계 (면접에서 말할 때)

1. **Greedy choice**: "매 단계에서 [기준]에 따라 선택"
2. **OPT 가정**: "최적해가 그리디와 다르다고 가정"
3. **Swap**: "OPT의 첫 선택을 그리디 선택으로 바꿔도 OPT 유지"
4. **귀납**: "남은 부분 문제도 동일 구조 → 그리디 = 최적"

이 4줄을 외워두면 어떤 그리디 문제든 증명 가능.

---

## 9. 다른 패턴과의 연결

### 9.1 Intervals 패턴 (03장)

```
Intervals (병합/삽입/겹침)  ⊂  Greedy
    ├── 정렬 + sweep         ← 그리디의 핵심 도구
    ├── Activity Selection   ← end time 정렬 그리디
    └── Non-overlapping      ← 동일 구조
```

Intervals 챕터의 모든 문제는 그리디. **정렬 키 + sweep**이 공통 골격.

### 9.2 Kruskal MST (그래프 11장)

```
[Kruskal 알고리즘]
1. 모든 edge를 weight 오름차순 정렬
2. Union-Find로 사이클 안 만드는 edge부터 추가
3. 정점 - 1개 edge 모이면 끝

→ 매 단계 "가장 가벼운 edge" 그리디 선택
→ Matroid 이론으로 정확성 증명
→ O(E log E) — 정렬 지배
```

MST는 그리디의 가장 우아한 응용 사례. Exchange argument 또는 cut property로 증명.

### 9.3 Dijkstra (그래프 11장)

```
[Dijkstra]
- 매번 "현재까지 거리 최소인 미방문 정점"을 그리디 선택
- 음수 간선 없으면 그리디 선택이 최단 거리임이 보장됨
- 음수 간선이 있으면 그리디 깨짐 → Bellman-Ford (DP)

PriorityQueue + 그리디의 정석.
```

### 9.4 Huffman Coding

```
[Huffman 알고리즘 — 압축 최적]
1. 모든 문자의 빈도를 min-heap에 넣음
2. 가장 작은 2개를 꺼내 합쳐 새 노드 (빈도 = 합)
3. heap에 다시 넣음
4. 1개 남을 때까지 반복 → 최적 prefix code 트리

→ 매번 "가장 작은 두 빈도" 그리디 결합
→ Exchange argument로 증명 (David Huffman, 1952 MIT 과제)
```

### 9.5 시니어 운영 연결

| 시스템 | 그리디 적용 |
|---|---|
| **K8s Scheduler** | 우선순위 기반 pod 배치 (FilteredPredicates + Priority score 최대) — 매 step 최선 |
| **CPU 스케줄링 (SJF)** | Shortest Job First — 평균 대기 시간 최소화 (그리디 증명됨) |
| **CDN Edge Selection** | 가장 가까운 edge로 라우팅 — Latency 최소 (Anycast + greedy) |
| **GC (G1)** | "가장 가비지 비율 높은 region"부터 collect — 효율 최대 (Garbage First) |
| **JIT 컴파일러 inline 결정** | call-site frequency 높은 것부터 inline — 성능 향상 그리디 |
| **Disk I/O 스케줄링 (SSTF)** | Shortest Seek Time First — head 이동 최소 |
| **Buffer pool eviction (LRU 근사)** | "가장 오래 안 쓴" 페이지 — 캐시 hit ratio 그리디 |
| **Network packet 라우팅** | BGP — 이웃 AS path 가장 짧은 경로 (정책 기반 그리디) |

**핵심 교훈**: 시스템 엔지니어링의 많은 결정은 **"지금 보이는 정보로 최선의 선택"** 이라는 그리디 철학을 따른다. 하지만 모든 상황에 통하지 않는다는 것도 함께 안다 — 예를 들어 SJF는 starvation 문제가 있어서 production에서는 aging을 더한 변형을 쓴다. **순수 그리디는 학문적, production은 그리디 + 보정** 패턴이다.

---

## 10. 마스터 체크리스트

문제를 보고 30초 안에 다음을 답할 수 있어야 한다.

- [ ] 그리디 신호 감지 (최대/최소, 즉시 선택, 정렬 후 sweep)
- [ ] **정렬 키**가 무엇인지 (start? end? value? ratio?)
- [ ] **Exchange Argument** 한 줄로 정당성 설명
- [ ] **반례** 시도 — 안 떠오르면 그리디 진행
- [ ] 시간 복잡도 즉답 (정렬 지배 시 O(N log N))
- [ ] 엣지 케이스: 빈 입력, 단일 원소, 동률, 음수 좌표, 오버플로우
- [ ] DP로 풀 수도 있는지 비교 (Stock 류, Jump Game)
- [ ] 다른 패턴 연결 (Intervals, Graph MST, Heap PQ)

이게 가능하면 그리디 챕터 마스터.

---

## 11. 백지에서 줄줄 풀어내는 핵심 4문장

1. **그리디 = 지역 최적 + 증명 가능한 전역 최적**. 증명 못 하면 DP.
2. **Exchange Argument**: OPT의 첫 선택을 그리디 선택으로 swap해도 OPT 유지 → 귀납적으로 그리디 = 최적.
3. **거의 모든 그리디는 O(N log N)**. 정렬 + 한 번 sweep. PQ는 동적 선택에.
4. **반례를 떠올리는 능력이 곧 실력**. 비표준 동전, 0/1 Knapsack, TSP는 그리디 안 됨.

이 4문장이 자연스럽게 나오면 시니어 수준이다.
