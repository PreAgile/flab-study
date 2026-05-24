# 03. Intervals (인터벌, 구간)

> "구간 병합? 정렬하고 합치면 되지" 라고 답하면 입문자.
> 마스터는 **시작/끝 쌍 입력을 보는 순간 "정렬 key를 start로 할지 end로 할지" 5초 안에 결정**하고, "동일 시점에 끝과 시작이 만나면 겹치는가" 같은 closed/open 경계를 면접관이 묻기 전에 짚으며, sweep line·heap·greedy 어떤 변형이든 막힘없이 쓴다.
>
> 이 챕터는 옵션·문법 외우기 대신 본질·왜·연결·운영 진단만 다룬다.

---

## 0. 인지 신호 — 30초 안에 "Interval 문제다" 판단하는 키워드

문제 설명에서 다음 신호가 보이면 99% Interval 패턴이다.

| 신호 | 예시 표현 | 떠올릴 패턴 |
|---|---|---|
| **시작/끝 쌍 입력** | `int[][] intervals` where `intervals[i] = [start, end]` | 정렬 + sweep |
| **병합 (merge)** | "겹치는 구간을 합쳐서", "merge overlapping intervals" | start 정렬 후 in-place 병합 |
| **겹침 판별 (overlap)** | "참석 가능한가", "충돌이 있는가", "can attend all meetings" | 정렬 후 인접 쌍 비교 |
| **회의실/리소스 개수** | "최소 회의실", "minimum rooms", "동시에 몇 개" | start-end 분리 sweep 또는 min-heap |
| **최소 제거** | "최소 몇 개를 빼야 안 겹치는가", "non-overlapping" | end 정렬 + greedy |
| **화살/풍선 (arrows)** | "최소 화살로 풍선 터트리기" | end 정렬 + greedy |
| **교집합 (intersection)** | "두 인터벌 리스트의 교집합" | 투포인터 + max(start)/min(end) |
| **삽입** | "새 인터벌을 넣고 다시 병합" | left/overlap/right 3구간 분할 |
| **달력/예약/스케줄링** | "calendar", "booking", "스케줄 충돌" | 위 모든 변형 |

**핵심**: 입력이 `[[s1,e1], [s2,e2], ...]` 형태이고, 문제가 "겹침"·"병합"·"개수"를 묻는다면 → 무조건 정렬부터 시작.

**정렬 key 결정 규칙** (이거 하나만 외우면 90% 풀린다):

| 목적 | 정렬 key | 이유 |
|---|---|---|
| 병합·삽입·겹침 판별 | **start 오름차순** | 인접 쌍만 비교하면 됨 |
| 최소 제거·최소 화살·greedy | **end 오름차순** | end가 빠를수록 다음 구간을 더 많이 수용 |
| 최소 회의실 | **start 오름차순** + min-heap(end) | 또는 start/end 분리 정렬 후 sweep |

---

## 1. 백지 그리기 — 3대 핵심 패턴 ASCII 다이어그램

### 1.1 패턴 A: 정렬 후 병합 (Merge)

```
입력:  [[1,3], [2,6], [8,10], [15,18]]

start 오름차순 정렬 (이미 정렬됨):

time:   0  1  2  3  4  5  6  7  8  9  10 11 12 13 14 15 16 17 18
        |  ●━━━━━●         |        |              |        |
        |     ●━━━━━━━━━●  |        |              |        |
        |                  ●━━━━━━━━●              |        |
        |                                          ●━━━━━━━━●

병합 진행:
  result = [[1,3]]
  next = [2,6]:  current.end=3 >= next.start=2  →  병합 → [1, max(3,6)] = [1,6]
  result = [[1,6]]
  next = [8,10]: current.end=6 <  next.start=8  →  새 구간 추가
  result = [[1,6], [8,10]]
  next = [15,18]: current.end=10 < 15  →  새 구간 추가
  result = [[1,6], [8,10], [15,18]]

출력:
time:   0  1  2  3  4  5  6  7  8  9  10  ... 15  ...  18
        |  ●━━━━━━━━━━━━━━━●     ●━━━━━━━●      ●━━━━━●
```

**핵심 통찰**: start로 정렬하면 인접 쌍 사이의 관계만 확인하면 된다. `current.end >= next.start`이면 겹침 → 병합, 아니면 새 구간 추가.

---

### 1.2 패턴 B: 시작-끝 분리 sweep (Meeting Rooms II)

같은 문제를 두 가지 방식으로 풀 수 있다.

**방식 1: start/end 배열 분리 정렬 + 투포인터 sweep**

```
입력:  [[0,30], [5,10], [15,20]]

starts = [0, 5, 15]      (오름차순)
ends   = [10, 20, 30]    (오름차순)

sweep:
  time=0 (start)   rooms++ → 1   nextStart→5
  time=5 (start)   rooms++ → 2   nextStart→15      ← 회의 0,5 동시
  time=10 (end)    rooms-- → 1   nextEnd→20        ← 회의 5 끝남? 아니, 가장 빠른 end=10
  time=15 (start)  rooms++ → 2   nextStart→끝      ← 회의 15 시작
  ...

답: max rooms = 2
```

**방식 2: min-heap(end 시간)**

```
입력: [[0,30], [5,10], [15,20]]   start 오름차순 정렬

heap = []  (회의실의 종료 시각들)

[0,30]:  heap이 비었거나 heap.peek() > 0  →  새 회의실 필요
         heap.push(30)  →  heap = [30]
         rooms = 1

[5,10]:  heap.peek() = 30 > 5  →  새 회의실 필요
         heap.push(10)  →  heap = [10, 30]
         rooms = 2

[15,20]: heap.peek() = 10 ≤ 15  →  기존 회의실 재사용
         heap.poll() → 10, heap.push(20) → heap = [20, 30]
         rooms = 2

답: rooms = 2
```

**왜 min-heap인가?**: "가장 빨리 끝나는 회의실이 비었나?"를 O(log n)에 확인. 비었으면 재사용, 아니면 새 회의실. heap 크기 = 동시 진행 회의 최대치 = 답.

---

### 1.3 패턴 C: end 정렬 + greedy (화살, 최소 제거)

```
입력:  [[10,16], [2,8], [1,6], [7,12]]      (Burst Balloons)

end 오름차순 정렬: [[1,6], [2,8], [7,12], [10,16]]

time:   1  2  3  4  5  6  7  8  9  10 11 12 13 14 15 16
        ●━━━━━━━━━━━━━●                                    ← 풍선 [1,6]
           ●━━━━━━━━━━━━━●                                 ← 풍선 [2,8]
                          ●━━━━━━━━━━━━━●                  ← 풍선 [7,12]
                                ●━━━━━━━━━━━━━━━━━━━━●    ← 풍선 [10,16]

화살 발사 전략:
  첫 풍선의 end=6에 화살을 쏜다 → [1,6], [2,8] 동시 터짐 (둘 다 6을 포함)
  다음 안 터진 풍선 = [7,12]. 그 end=12에 화살 → [7,12], [10,16] 동시 터짐.

  arrows = 2

화살 위치 표시:
        ↓                       ↓
time:   1  2  3  4  5  6  7  8  9  10 11 12 13 14 15 16
                       ✗                       ✗
```

**왜 end 정렬인가?**: 화살 1발로 최대한 많은 풍선을 터트리려면, **가장 일찍 끝나는 풍선의 end**에 쏘는 게 최적. 그래야 뒤에 시작하는 풍선들 중 그 end를 포함하는 것들이 모두 터진다. Greedy의 exchange argument로 증명 가능.

---

### 1.4 두 인터벌의 겹침 조건 (closed interval)

```
case 1: 완전 분리
  A: ●━━━●
  B:           ●━━━●
  → A.end < B.start (분리)

case 2: 끝점만 겹침 (closed interval에선 겹침)
  A: ●━━━●
  B:     ●━━━●
  → A.end == B.start  (closed: 겹침, open: 분리)

case 3: 일부 겹침
  A: ●━━━━━●
  B:    ●━━━━━●
  → A.end > B.start && A.start < B.end

case 4: 포함
  A: ●━━━━━━━━━━━●
  B:    ●━━━●
  → A.start ≤ B.start && B.end ≤ A.end

통합 겹침 조건 (closed):  A.start ≤ B.end  AND  B.start ≤ A.end
                          ↔ max(A.start, B.start) ≤ min(A.end, B.end)
```

**경계 처리는 문제마다 다르다**. LeetCode 56(Merge)는 closed → `[1,4],[4,5]` 병합 가능. LeetCode 252(Meeting Rooms)는 한 회의가 끝나는 순간 다음 회의 시작 OK → open처럼 처리. **문제 정의를 반드시 먼저 확인**.

---

## 2. 직관과 정의

### 2.1 Interval의 수학적 정의

| 표기 | 의미 | Java에서 보통 |
|---|---|---|
| `[a, b]` | closed interval, a ≤ x ≤ b | `int[]{a, b}` |
| `[a, b)` | half-open, a ≤ x < b | 시간 구간/배열 인덱스에서 자주 |
| `(a, b)` | open interval, a < x < b | 거의 안 씀 |

**LeetCode 56 기본 가정**: closed `[start, end]`. 그래서 `[1,4]`와 `[4,5]`는 겹친다고 본다.

**시간/날짜 구간**: 보통 half-open `[start, end)`로 모델링. "9시 회의는 10시까지"는 9:00 ≤ t < 10:00. 그래야 `[9,10)`과 `[10,11)`이 인접해도 겹치지 않는다. **운영 코드에선 half-open이 사실상 표준** — Java `Range`, ICU, Google Calendar API 모두 half-open.

### 2.2 겹침 (overlap)의 본질

두 구간이 "공통점을 하나라도 공유하는가"가 겹침. 수학적으로:

```
A ∩ B ≠ ∅   ↔   max(A.start, B.start) ≤ min(A.end, B.end)    (closed)
A ∩ B ≠ ∅   ↔   max(A.start, B.start) <  min(A.end, B.end)    (half-open)
```

**왜 max/min 형태인가**: 교집합의 시작은 두 시작 중 늦은 쪽, 끝은 두 끝 중 빠른 쪽. 시작 > 끝이면 공집합.

### 2.3 정렬 key의 의미

- **start로 정렬**: "시간 순서대로 보면" 이라는 자연스러운 진행. 인접 쌍만 보면 전체 관계를 파악할 수 있다 (transitive merge가능).
- **end로 정렬**: "가장 빨리 끝나는 것부터" — greedy choice. activity selection 정리: end 빠른 것을 고르면 남은 시간이 최대 → 뒤에 고를 수 있는 활동 개수가 최대.

### 2.4 Sweep Line이라는 패러다임

**Sweep line**: 수직선이 좌(작은 시간)에서 우(큰 시간)로 쓸고 지나가며, 만나는 이벤트(start/end)마다 상태를 갱신하는 알고리즘 패러다임.

```
이벤트 큐:  [(0,+1), (5,+1), (10,-1), (15,+1), (20,-1), (30,-1)]
            (+1 = start, -1 = end)

sweep:    time → 0,   5,   10,  15,  20,  30
          cnt →  1,   2,   1,   2,   1,   0
                              ↑
                          max = 2 (= 최소 회의실)
```

핵심 통찰: **인터벌 문제의 90%는 sweep line의 변형**이다. 정렬 후 한 방향으로 훑는 구조 = 시간 복잡도 O(n log n).

---

## 3. Java 템플릿 — 5가지 핵심 변형

### 3.1 변형 1: Merge Intervals (병합)

```java
import java.util.*;

class MergeIntervals {
    public int[][] merge(int[][] intervals) {
        if (intervals.length <= 1) return intervals;

        // 1. start 오름차순 정렬
        Arrays.sort(intervals, (a, b) -> Integer.compare(a[0], b[0]));

        List<int[]> result = new ArrayList<>();
        int[] current = intervals[0];
        result.add(current);

        // 2. 인접 쌍 비교: current.end >= next.start이면 병합
        for (int i = 1; i < intervals.length; i++) {
            int[] next = intervals[i];
            if (current[1] >= next[0]) {
                current[1] = Math.max(current[1], next[1]);   // 병합
            } else {
                current = next;
                result.add(current);
            }
        }
        return result.toArray(new int[0][]);
    }
}
```

**왜 `Integer.compare(a[0], b[0])`인가**: `a[0] - b[0]`은 음수 overflow 위험. `Integer.MIN_VALUE - 1` 같은 케이스 방어. 운영에서 panic을 부르는 미묘한 버그의 단골 출처.

### 3.2 변형 2: Insert Interval (이미 정렬된 리스트에 삽입)

```java
class InsertInterval {
    public int[][] insert(int[][] intervals, int[] newInterval) {
        List<int[]> result = new ArrayList<>();
        int i = 0, n = intervals.length;

        // 1. newInterval보다 완전히 왼쪽인 구간들 (end < newInterval.start)
        while (i < n && intervals[i][1] < newInterval[0]) {
            result.add(intervals[i++]);
        }

        // 2. 겹치는 구간들을 newInterval에 흡수 (start <= newInterval.end)
        while (i < n && intervals[i][0] <= newInterval[1]) {
            newInterval[0] = Math.min(newInterval[0], intervals[i][0]);
            newInterval[1] = Math.max(newInterval[1], intervals[i][1]);
            i++;
        }
        result.add(newInterval);

        // 3. 남은 오른쪽 구간들
        while (i < n) result.add(intervals[i++]);

        return result.toArray(new int[0][]);
    }
}
```

**O(n) 가능 이유**: 입력이 이미 정렬되어 있다는 전제. 정렬 비용 없이 단일 패스.

### 3.3 변형 3: 겹침 카운트 / 충돌 판별 (Meeting Rooms I)

```java
class MeetingRoomsI {
    public boolean canAttendAllMeetings(int[][] intervals) {
        Arrays.sort(intervals, (a, b) -> Integer.compare(a[0], b[0]));
        for (int i = 1; i < intervals.length; i++) {
            if (intervals[i][0] < intervals[i-1][1]) return false;  // 겹침
        }
        return true;
    }
}
```

**`<` vs `<=` 의 차이**: 회의실에선 한 회의 끝나는 즉시 다음 회의 가능 → `<` 사용 (`end == start`는 허용). 병합 문제에선 같은 시점도 연결 → `<=` 또는 `>=` 사용. **문제마다 다르다**.

### 3.4 변형 4: 최소 회의실 (Meeting Rooms II, min-heap)

```java
import java.util.*;

class MeetingRoomsII {
    public int minMeetingRooms(int[][] intervals) {
        if (intervals.length == 0) return 0;

        // 1. start 오름차순
        Arrays.sort(intervals, (a, b) -> Integer.compare(a[0], b[0]));

        // 2. min-heap: 각 회의실의 종료 시각
        PriorityQueue<Integer> heap = new PriorityQueue<>();

        for (int[] interval : intervals) {
            // 가장 빨리 끝나는 방이 이미 비었다면 재사용
            if (!heap.isEmpty() && heap.peek() <= interval[0]) {
                heap.poll();
            }
            heap.offer(interval[1]);
        }
        return heap.size();
    }
}
```

**대안: start/end 분리 정렬 + 투포인터 sweep**

```java
class MeetingRoomsIISweep {
    public int minMeetingRooms(int[][] intervals) {
        int n = intervals.length;
        int[] starts = new int[n], ends = new int[n];
        for (int i = 0; i < n; i++) { starts[i] = intervals[i][0]; ends[i] = intervals[i][1]; }
        Arrays.sort(starts);
        Arrays.sort(ends);

        int rooms = 0, maxRooms = 0, e = 0;
        for (int s = 0; s < n; s++) {
            if (starts[s] < ends[e]) {
                rooms++;
                maxRooms = Math.max(maxRooms, rooms);
            } else {
                e++;       // 한 회의실이 비었음
            }
        }
        return maxRooms;
    }
}
```

**둘의 trade-off**: heap은 직관적이고 일반화하기 쉽다 (회의실마다 다른 속성을 저장 가능). 분리 sweep은 메모리/상수배 빠르지만 "어떤 회의가 어느 방을 썼는지"는 잃는다. 운영에선 보통 heap을 선호 — 추적 가능성이 더 중요.

### 3.5 변형 5: end 정렬 + greedy (화살, 최소 제거)

```java
class MinArrows {
    public int findMinArrowShots(int[][] points) {
        if (points.length == 0) return 0;

        // end 오름차순 정렬 (overflow 방지)
        Arrays.sort(points, (a, b) -> Integer.compare(a[1], b[1]));

        int arrows = 1;
        long lastShot = points[0][1];     // long으로 overflow 방어

        for (int i = 1; i < points.length; i++) {
            if (points[i][0] > lastShot) {
                arrows++;
                lastShot = points[i][1];
            }
        }
        return arrows;
    }
}
```

**왜 `long lastShot`인가**: LeetCode 452 입력에 `Integer.MAX_VALUE`가 들어올 수 있고, `points[i][0] > lastShot` 비교 직전 자동 promotion이 일어나도 `points[0][1]` 자체가 `Integer.MAX_VALUE`인 경우는 안전하지만, end 정렬에서 `a[1] - b[1]`를 썼다면 overflow 폭탄. 운영 코드는 **default가 long 또는 Integer.compare**.

---

## 4. Kotlin 템플릿 — 동일 5변형의 관용 표현

### 4.1 Merge Intervals (Kotlin)

```kotlin
fun merge(intervals: Array<IntArray>): Array<IntArray> {
    if (intervals.size <= 1) return intervals

    intervals.sortBy { it[0] }            // start 오름차순
    val result = mutableListOf<IntArray>()
    var current = intervals[0]
    result.add(current)

    for (i in 1 until intervals.size) {
        val next = intervals[i]
        if (current[1] >= next[0]) {
            current[1] = maxOf(current[1], next[1])
        } else {
            current = next
            result.add(current)
        }
    }
    return result.toTypedArray()
}
```

**Kotlin 관용 표현**: `sortBy { it[0] }` — `Comparator` 없이 셀렉터 함수 전달. 가독성 압승.

### 4.2 Insert Interval (Kotlin)

```kotlin
fun insert(intervals: Array<IntArray>, newInterval: IntArray): Array<IntArray> {
    val result = mutableListOf<IntArray>()
    var i = 0
    val n = intervals.size
    val merged = newInterval.copyOf()      // 입력 불변성 유지

    while (i < n && intervals[i][1] < merged[0]) result.add(intervals[i++])
    while (i < n && intervals[i][0] <= merged[1]) {
        merged[0] = minOf(merged[0], intervals[i][0])
        merged[1] = maxOf(merged[1], intervals[i][1])
        i++
    }
    result.add(merged)
    while (i < n) result.add(intervals[i++])

    return result.toTypedArray()
}
```

### 4.3 Meeting Rooms I (Kotlin)

```kotlin
fun canAttendAll(intervals: Array<IntArray>): Boolean {
    intervals.sortBy { it[0] }
    return intervals.zipWithNext().all { (a, b) -> a[1] <= b[0] }
}
```

**`zipWithNext`**: Kotlin이 인접 쌍 비교에 제공하는 sugar. `[a,b,c,d] → [(a,b),(b,c),(c,d)]`. Interval 인접 비교 패턴에 환상적으로 어울린다.

### 4.4 Meeting Rooms II (Kotlin, heap)

```kotlin
import java.util.PriorityQueue

fun minMeetingRooms(intervals: Array<IntArray>): Int {
    if (intervals.isEmpty()) return 0
    intervals.sortBy { it[0] }

    val heap = PriorityQueue<Int>()
    for (interval in intervals) {
        if (heap.isNotEmpty() && heap.peek() <= interval[0]) heap.poll()
        heap.offer(interval[1])
    }
    return heap.size
}
```

### 4.5 Min Arrows (Kotlin)

```kotlin
fun findMinArrowShots(points: Array<IntArray>): Int {
    if (points.isEmpty()) return 0
    points.sortWith(compareBy { it[1] })    // end 정렬 (overflow 안전)

    var arrows = 1
    var lastShot = points[0][1].toLong()

    for (i in 1 until points.size) {
        if (points[i][0] > lastShot) {
            arrows++
            lastShot = points[i][1].toLong()
        }
    }
    return arrows
}
```

**`compareBy { it[1] }`**: `(a,b) -> a[1] - b[1]` overflow 위험을 원천 봉쇄. Kotlin이 이런 비교 작성 시 더 안전한 default를 제공.

---

## 5. 시간/공간 복잡도

### 5.1 왜 거의 모든 인터벌 문제가 O(n log n)인가

정렬이 지배적. 정렬 후 단일 패스는 O(n), heap을 곁들여도 각 op O(log n) × n = O(n log n). 따라서 **정렬을 피할 수 없는 한 O(n log n) 미만은 불가능**.

| 변형 | 시간 | 공간 | 지배 비용 |
|---|---|---|---|
| Merge | O(n log n) | O(n) (결과 저장) | 정렬 |
| Insert (이미 정렬됨) | **O(n)** | O(n) | 단일 패스 |
| Meeting Rooms I | O(n log n) | O(1) ~ O(log n) | 정렬 |
| Meeting Rooms II (heap) | O(n log n) | O(n) | 정렬 + heap |
| Meeting Rooms II (sweep) | O(n log n) | O(n) | 정렬 |
| Non-overlapping (greedy) | O(n log n) | O(1) | 정렬 |
| Min Arrows | O(n log n) | O(1) | 정렬 |
| Interval Intersections | **O(n+m)** | O(n+m) | 두 리스트가 정렬됨 |

### 5.2 정렬을 피하는 경우 = O(n) 가능

1. **입력이 이미 정렬됨** (Insert Interval, Interval List Intersections) → O(n)
2. **카운팅 가능한 작은 범위** — 시간이 정수이고 범위가 작으면 sweep을 bucket counting으로 → O(n + range). 거의 안 나옴.
3. **스트리밍 도착** — 새 인터벌이 정렬된 채로 들어오면 BST/Segment Tree로 op당 O(log n).

### 5.3 공간 — in-place vs 새 리스트

`merge`는 보통 새 List를 만들지만, 정렬된 입력 위에서 in-place로 덮어쓰면 O(1) 추가 공간. 면접에서 "메모리 줄이려면?" 꼬리질문이 나오면 in-place merge를 보여주면 된다.

```java
// in-place merge (정렬 후)
int write = 0;
for (int i = 1; i < intervals.length; i++) {
    if (intervals[write][1] >= intervals[i][0]) {
        intervals[write][1] = Math.max(intervals[write][1], intervals[i][1]);
    } else {
        intervals[++write] = intervals[i];
    }
}
// 결과 = intervals[0..write]
```

---

## 6. 대표 문제 8개 — 라이브 코딩 합격 패턴

### 6.1 LeetCode 56 — Merge Intervals (Medium)

**문제 요약**: 인터벌 배열에서 겹치는 것들을 모두 병합해 반환.

**접근**: start 정렬 → 인접 쌍 비교 → `current.end >= next.start`면 병합.

**Java 풀이**:
```java
public int[][] merge(int[][] intervals) {
    if (intervals.length <= 1) return intervals;
    Arrays.sort(intervals, (a, b) -> Integer.compare(a[0], b[0]));
    List<int[]> result = new ArrayList<>();
    int[] cur = intervals[0];
    result.add(cur);
    for (int i = 1; i < intervals.length; i++) {
        if (cur[1] >= intervals[i][0]) {
            cur[1] = Math.max(cur[1], intervals[i][1]);
        } else {
            cur = intervals[i];
            result.add(cur);
        }
    }
    return result.toArray(new int[0][]);
}
```

**Kotlin 풀이**:
```kotlin
fun merge(intervals: Array<IntArray>): Array<IntArray> {
    if (intervals.size <= 1) return intervals
    intervals.sortBy { it[0] }
    val out = mutableListOf<IntArray>()
    var cur = intervals[0]
    out.add(cur)
    for (i in 1 until intervals.size) {
        if (cur[1] >= intervals[i][0]) cur[1] = maxOf(cur[1], intervals[i][1])
        else { cur = intervals[i]; out.add(cur) }
    }
    return out.toTypedArray()
}
```

**복잡도**: O(n log n) / O(n).

**함정**:
- `result.add(intervals[0].clone())`을 안 하면 입력 배열이 변형됨 (`cur[1] = ...`). 면접관이 "입력 보존이 요구되면?" 꼬리질문하면 clone 추가.
- closed interval 가정: `[1,4],[4,5]` → `[1,5]`. open이라면 `>` 사용해야 함.

---

### 6.2 LeetCode 57 — Insert Interval (Medium)

**문제 요약**: 이미 정렬되고 겹치지 않는 인터벌 리스트에 새 인터벌을 삽입하고 결과를 다시 정렬·병합된 형태로 반환.

**접근**: 3구간 분할 — 왼쪽(완전 분리) / 겹치는 부분(흡수) / 오른쪽(완전 분리).

**Java 풀이**:
```java
public int[][] insert(int[][] intervals, int[] newInterval) {
    List<int[]> result = new ArrayList<>();
    int i = 0, n = intervals.length;

    while (i < n && intervals[i][1] < newInterval[0]) result.add(intervals[i++]);

    int[] merged = new int[]{newInterval[0], newInterval[1]};
    while (i < n && intervals[i][0] <= merged[1]) {
        merged[0] = Math.min(merged[0], intervals[i][0]);
        merged[1] = Math.max(merged[1], intervals[i][1]);
        i++;
    }
    result.add(merged);

    while (i < n) result.add(intervals[i++]);
    return result.toArray(new int[0][]);
}
```

**Kotlin 풀이**:
```kotlin
fun insert(intervals: Array<IntArray>, newInterval: IntArray): Array<IntArray> {
    val out = mutableListOf<IntArray>()
    var i = 0
    val n = intervals.size
    val merged = intArrayOf(newInterval[0], newInterval[1])

    while (i < n && intervals[i][1] < merged[0]) out.add(intervals[i++])
    while (i < n && intervals[i][0] <= merged[1]) {
        merged[0] = minOf(merged[0], intervals[i][0])
        merged[1] = maxOf(merged[1], intervals[i][1])
        i++
    }
    out.add(merged)
    while (i < n) out.add(intervals[i++])
    return out.toTypedArray()
}
```

**복잡도**: O(n) / O(n).

**함정**:
- "겹친다"의 경계: `intervals[i][0] <= merged[1]`. `<`로 잘못 쓰면 `[1,5]`와 `[5,7]`이 안 합쳐짐.
- newInterval이 끝에 추가되어야 하는데 result에 잊고 안 넣는 경우. **항상 `result.add(merged)`는 무조건 1번 수행**되어야 함.
- 입력이 비어있는 케이스 (`intervals = []`) → newInterval만 결과.

---

### 6.3 LeetCode 252 — Meeting Rooms (Easy)

**문제 요약**: 모든 회의를 한 사람이 참석할 수 있는가?

**접근**: start 정렬 후 인접 쌍 비교. 하나라도 겹치면 false.

**Java 풀이**:
```java
public boolean canAttendMeetings(int[][] intervals) {
    Arrays.sort(intervals, (a, b) -> Integer.compare(a[0], b[0]));
    for (int i = 1; i < intervals.length; i++) {
        if (intervals[i][0] < intervals[i-1][1]) return false;
    }
    return true;
}
```

**Kotlin 풀이**:
```kotlin
fun canAttendMeetings(intervals: Array<IntArray>): Boolean {
    intervals.sortBy { it[0] }
    return intervals.zipWithNext().all { (a, b) -> a[1] <= b[0] }
}
```

**복잡도**: O(n log n) / O(1).

**함정**:
- `<` vs `<=` — 회의에선 `end == start`는 OK (10시 끝/10시 시작). 문제 정의 확인 필수.
- 빈 배열은 true (참석할 게 없음).

---

### 6.4 LeetCode 253 — Meeting Rooms II (Medium) ★ 단골

**문제 요약**: 모든 회의를 진행하려면 회의실이 최소 몇 개 필요한가?

**접근 1 (min-heap)**: start 정렬 → 각 회의에 대해 heap의 가장 빠른 end 확인 → 비었으면 재사용, 아니면 추가.

**접근 2 (분리 sweep)**: starts·ends 배열 분리 정렬 → 투포인터로 동시점 카운트.

**Java 풀이 (heap)**:
```java
public int minMeetingRooms(int[][] intervals) {
    if (intervals.length == 0) return 0;
    Arrays.sort(intervals, (a, b) -> Integer.compare(a[0], b[0]));
    PriorityQueue<Integer> heap = new PriorityQueue<>();
    for (int[] interval : intervals) {
        if (!heap.isEmpty() && heap.peek() <= interval[0]) heap.poll();
        heap.offer(interval[1]);
    }
    return heap.size();
}
```

**Kotlin 풀이 (분리 sweep)**:
```kotlin
fun minMeetingRooms(intervals: Array<IntArray>): Int {
    val n = intervals.size
    if (n == 0) return 0
    val starts = IntArray(n) { intervals[it][0] }.also { it.sort() }
    val ends   = IntArray(n) { intervals[it][1] }.also { it.sort() }

    var rooms = 0; var maxRooms = 0; var e = 0
    for (s in 0 until n) {
        if (starts[s] < ends[e]) { rooms++; maxRooms = maxOf(maxRooms, rooms) }
        else { e++ }
    }
    return maxRooms
}
```

**복잡도**: O(n log n) / O(n).

**함정**:
- `heap.peek() <= interval[0]`에서 `<=` — `end == start`인 회의실은 재사용 가능 (회의 정의상).
- "최소"가 어떤 의미인지: 동시 진행 회의의 최대치 = 답. 이걸 못 잡으면 O(n²) brute force로 빠짐.
- 분리 sweep은 "동시점에 끝과 시작이 만나면" 어떻게 처리할지 정렬 안정성에 의존 → end가 먼저 와야 안전.

**시니어 운영 관점**: 이게 바로 **connection pool 사이즈 결정** 알고리즘이다. 각 요청을 인터벌로 보고 동시 진행 최대치 = 최소 connection 개수. JMeter 로그를 인터벌로 변환 → MR2를 돌리면 DB connection pool sizing이 데이터 기반으로 나온다.

---

### 6.5 LeetCode 435 — Non-overlapping Intervals (Medium)

**문제 요약**: 겹치지 않는 상태로 만들기 위해 제거해야 하는 최소 인터벌 개수.

**접근**: end 오름차순 정렬 → greedy하게 end가 빠른 것부터 유지, 다음 것이 겹치면 제거.

**왜 end 정렬?**: activity selection. end가 빠를수록 뒤에 들어갈 자리가 더 많이 남음. exchange argument로 증명: 만약 end가 늦은 것을 선택했다면, 그것을 end가 더 빠른 것으로 바꿔도 답이 나빠지지 않음.

**Java 풀이**:
```java
public int eraseOverlapIntervals(int[][] intervals) {
    if (intervals.length == 0) return 0;
    Arrays.sort(intervals, (a, b) -> Integer.compare(a[1], b[1]));

    int kept = 1;
    int lastEnd = intervals[0][1];
    for (int i = 1; i < intervals.length; i++) {
        if (intervals[i][0] >= lastEnd) {
            kept++;
            lastEnd = intervals[i][1];
        }
    }
    return intervals.length - kept;
}
```

**Kotlin 풀이**:
```kotlin
fun eraseOverlapIntervals(intervals: Array<IntArray>): Int {
    if (intervals.isEmpty()) return 0
    intervals.sortWith(compareBy { it[1] })
    var kept = 1
    var lastEnd = intervals[0][1]
    for (i in 1 until intervals.size) {
        if (intervals[i][0] >= lastEnd) {
            kept++
            lastEnd = intervals[i][1]
        }
    }
    return intervals.size - kept
}
```

**복잡도**: O(n log n) / O(1).

**함정**:
- start 정렬로도 풀 수 있지만 logic이 더 복잡 (겹치면 더 짧은 것을 keep). end 정렬이 항상 더 깔끔.
- "겹친다"의 경계: `intervals[i][0] >= lastEnd`이 keep 조건. closed interval인지 half-open인지에 따라 `>=` vs `>` 결정.

---

### 6.6 LeetCode 452 — Minimum Number of Arrows to Burst Balloons (Medium)

**문제 요약**: x축 위 풍선 인터벌들. 수직으로 쏘는 화살로 모두 터트릴 때 최소 화살 개수.

**접근**: end 정렬 → 첫 풍선의 end에 쏘기 → 그 end보다 시작이 큰 다음 풍선에 새 화살.

**Java 풀이**:
```java
public int findMinArrowShots(int[][] points) {
    if (points.length == 0) return 0;
    Arrays.sort(points, (a, b) -> Integer.compare(a[1], b[1]));

    int arrows = 1;
    long shot = points[0][1];
    for (int i = 1; i < points.length; i++) {
        if (points[i][0] > shot) {
            arrows++;
            shot = points[i][1];
        }
    }
    return arrows;
}
```

**Kotlin 풀이**:
```kotlin
fun findMinArrowShots(points: Array<IntArray>): Int {
    if (points.isEmpty()) return 0
    points.sortWith(compareBy { it[1] })

    var arrows = 1
    var shot = points[0][1].toLong()
    for (i in 1 until points.size) {
        if (points[i][0] > shot) {
            arrows++
            shot = points[i][1].toLong()
        }
    }
    return arrows
}
```

**복잡도**: O(n log n) / O(1).

**함정**:
- `a[1] - b[1]` overflow — LeetCode 452는 `Integer.MIN_VALUE`/`MAX_VALUE`가 자주 등장. `Integer.compare` 또는 `compareBy` 필수.
- 경계: 풍선이 `[1,6],[6,10]`이면 한 화살로 터짐 (x=6에서). 그래서 `>`이지 `>=`이 아님.
- 435와 거의 같은 구조 — 한쪽은 "제거", 한쪽은 "한 그룹". 본질적으로 동일한 greedy.

---

### 6.7 LeetCode 986 — Interval List Intersections (Medium)

**문제 요약**: 정렬된 두 인터벌 리스트의 교집합 리스트 반환.

**접근**: 투포인터. `max(a.start, b.start)` 와 `min(a.end, b.end)`로 교집합 생성. 끝이 빠른 쪽의 포인터 전진.

**Java 풀이**:
```java
public int[][] intervalIntersection(int[][] A, int[][] B) {
    List<int[]> result = new ArrayList<>();
    int i = 0, j = 0;
    while (i < A.length && j < B.length) {
        int lo = Math.max(A[i][0], B[j][0]);
        int hi = Math.min(A[i][1], B[j][1]);
        if (lo <= hi) result.add(new int[]{lo, hi});
        if (A[i][1] < B[j][1]) i++; else j++;
    }
    return result.toArray(new int[0][]);
}
```

**Kotlin 풀이**:
```kotlin
fun intervalIntersection(A: Array<IntArray>, B: Array<IntArray>): Array<IntArray> {
    val out = mutableListOf<IntArray>()
    var i = 0; var j = 0
    while (i < A.size && j < B.size) {
        val lo = maxOf(A[i][0], B[j][0])
        val hi = minOf(A[i][1], B[j][1])
        if (lo <= hi) out.add(intArrayOf(lo, hi))
        if (A[i][1] < B[j][1]) i++ else j++
    }
    return out.toTypedArray()
}
```

**복잡도**: O(n + m) / O(n + m).

**함정**:
- "왜 끝이 빠른 쪽을 전진?" — 끝이 빠른 인터벌은 이후 어느 인터벌과도 더 이상 교집합을 만들 수 없음 (다음 인터벌의 start는 현재보다 크거나 같음 + 현재 end보다 큼).
- `lo <= hi` 조건 (closed). half-open이면 `lo < hi`.
- 입력이 비정렬이면 이 알고리즘 깨짐 → 그 경우 정렬해서 O((n+m)log(n+m))로 전환.

---

### 6.8 Programmers — 단속카메라 (Lv.3)

**문제 요약**: 고속도로 위 차량들의 진입·진출 위치 (인터벌)가 주어진다. 모든 차량을 한 번 이상 단속카메라로 찍으려면 최소 카메라 개수.

**접근**: LeetCode 452 (화살)과 본질적으로 동일. **진출 위치(end) 오름차순 정렬** → 가장 빨리 진출하는 차량의 end에 카메라 설치 → 그 카메라 위치보다 진입(start)이 큰 차량 만나면 새 카메라.

**왜 end 정렬?**: end가 빠른 차량부터 처리하면, 그 차량의 마지막 위치(=end)에 카메라를 설치하는 것이 다른 차량을 최대한 많이 포함시키는 선택. greedy의 exchange argument로 증명.

**Java 풀이**:
```java
import java.util.Arrays;

class Solution {
    public int solution(int[][] routes) {
        Arrays.sort(routes, (a, b) -> Integer.compare(a[1], b[1]));

        int cameras = 0;
        long cameraAt = Long.MIN_VALUE;
        for (int[] r : routes) {
            if (r[0] > cameraAt) {
                cameras++;
                cameraAt = r[1];
            }
        }
        return cameras;
    }
}
```

**Kotlin 풀이**:
```kotlin
class Solution {
    fun solution(routes: Array<IntArray>): Int {
        routes.sortWith(compareBy { it[1] })

        var cameras = 0
        var cameraAt = Long.MIN_VALUE
        for (r in routes) {
            if (r[0] > cameraAt) {
                cameras++
                cameraAt = r[1].toLong()
            }
        }
        return cameras
    }
}
```

**복잡도**: O(n log n) / O(1).

**함정**:
- 입력 범위가 `-30000 ~ 30000`이라 overflow는 안 나지만 `cameraAt` 초기값을 `Integer.MIN_VALUE`로 잡으면 `r[0] > cameraAt` 비교에서 보통은 안전. 그래도 습관적으로 long으로.
- `>` vs `>=`: `r[0] == cameraAt`이면 그 차량도 찍힌 것 (closed interval) → `>`만 트리거.

**연결**: LeetCode 452와 1:1 매핑. 한쪽은 화살, 한쪽은 카메라. **그리디 + end 정렬 = 동일 패턴**임을 인식하는 것이 마스터의 표시.

---

## 7. 함정·엣지케이스 — 면접관이 묻기 전에 짚어야 할 것

### 7.1 동일 시점에 끝-시작 동시 — `>=` vs `>` 결정

```
A: ●━━━●     A.end = 5
B:      ●━━━●  B.start = 5

closed:    A와 B는 5에서 만남 → 겹친다고 봄 (>= 트리거)
half-open: 5는 B에만 포함 → 겹치지 않음 (> 트리거)
```

| 문제 | 권장 비교 | 이유 |
|---|---|---|
| LeetCode 56 Merge | `current.end >= next.start` | closed, 연결 가정 |
| LeetCode 252 Meeting Rooms | `intervals[i][0] < intervals[i-1][1]` | 회의실은 끝-시작 인접 OK |
| LeetCode 253 Meeting Rooms II | `heap.peek() <= interval[0]` | 동일 |
| LeetCode 435 Non-overlap | `intervals[i][0] >= lastEnd` | closed, end == next.start 허용 (touch) |
| LeetCode 452 Arrows | `points[i][0] > shot` | closed, end == next.start면 같은 화살 |

**면접 포인트**: 문제 정의를 명시적으로 확인하지 않고 코드를 시작하면 100% 깨진다. "closed interval로 가정하나요?" 또는 "두 회의가 같은 시각에 끝나고 시작하면 한 사람이 둘 다 갈 수 있나요?"가 첫 질문이어야 한다.

### 7.2 정렬 key 선택 실수

```
[[1,4], [2,3]]을 start로 정렬 → 그대로

LeetCode 435 (non-overlapping)에서 start 정렬로 풀면:
  keep [1,4], next [2,3]: 겹침 → 제거. 하지만 [2,3]을 keep하고 [1,4]를 제거하는 게 더 나음!

end 정렬로 풀면:
  [[2,3], [1,4]]: keep [2,3], next [1,4]: start=1 < end=3 → 제거. answer = 1. 정답.
```

**규칙**:
- 병합·삽입·인접 충돌 → start 정렬.
- greedy 선택 (최대 keep, 최소 제거) → **end 정렬이 거의 항상 정답**.
- 회의실 II → start 정렬 + heap, 또는 분리 sweep.

### 7.3 빈 배열 / 단일 인터벌

```java
if (intervals.length == 0) return new int[0][];      // 빈 결과
if (intervals.length == 1) return intervals;         // 그대로
```

거의 모든 인터벌 코드의 첫 두 줄. 안 넣으면 NullPointer/IndexOutOfBounds 면접관 1점 감점.

### 7.4 정수 overflow

```java
// BAD — Integer.MIN_VALUE - 1 = MAX_VALUE (overflow)
Arrays.sort(intervals, (a, b) -> a[0] - b[0]);

// GOOD
Arrays.sort(intervals, (a, b) -> Integer.compare(a[0], b[0]));
```

LeetCode 452, 218 (Skyline) 등은 `Integer.MAX_VALUE`가 정말 입력으로 들어온다. **default를 `Integer.compare` / `compareBy`로 굳히는 게 운영 안전**.

### 7.5 입력 변형 (in-place 사이드 이펙트)

```java
result.add(intervals[0]);            // BAD — intervals 배열의 reference 공유
// 이후 intervals[0][1] = ... 하면 result에도 반영됨

result.add(intervals[0].clone());    // GOOD
```

라이브 코딩에서 면접관이 "이 함수 호출 후 입력이 보존되어야 한다면?" 묻는 단골 꼬리. clone()/copyOf 한 줄 추가하면 됨.

### 7.6 unsorted 입력을 sorted라고 가정

LeetCode 57(Insert), 986(Intersections)은 **입력이 이미 정렬되어 있다는 전제**. 면접에서 같은 문제를 "정렬 보장 없음"으로 바꾸면 O((n+m)log(n+m))로 답이 달라짐.

### 7.7 비교가 안정 정렬을 가정하는 경우

start와 end 분리 sweep에서 `starts[s] == ends[e]`인 시점이 있을 수 있다. 한 회의가 끝나는 순간 다른 회의가 시작하는 경우:
- "끝나는 회의 = 종료" 먼저 처리해야 회의실 재사용 가능 → end 우선.
- 코드에서 `starts[s] < ends[e]`로 strict `<`를 쓰면 자동으로 end 우선 처리됨.

### 7.8 시간 단위 — minute vs millisecond vs Instant

실무에선 `LocalDateTime`/`Instant`로 인터벌을 모델링하는 경우가 많다. 코딩 테스트는 int지만, 면접 꼬리에서 "실무에선?" 물으면:
- `Duration.between(start, end)`로 길이 계산.
- `ChronoUnit.MINUTES.between(...)`로 단위 통일.
- TZ 다를 때는 `ZonedDateTime` → `Instant`로 정규화 후 비교.

---

## 8. 꼬리질문 트리 — 면접관이 파고드는 다음 질문

### 8.1 "인터벌이 동적으로 추가/삭제된다면?" — Segment Tree / Interval Tree

정적 인터벌 N개 → O(n log n) 정렬 후 처리.
**동적**으로 인터벌이 들어오고 빠지면 정렬 자체가 비싸짐. 대안:

| 자료구조 | 시간 (op당) | 용도 |
|---|---|---|
| TreeMap | O(log n) | 인접 인터벌 조회 (floor/ceiling) — LeetCode 715 Range Module |
| Segment Tree | O(log n) | 구간 합·최댓값·갱신 — LeetCode 218 Skyline의 알트풀이 |
| Interval Tree (augmented BBST) | O(log n) | "이 점과 겹치는 인터벌 모두" — 일정관리, geometric overlap |
| Fenwick Tree (BIT) | O(log n) | 카운팅 sweep, prefix 합 |

**LeetCode 715 (Range Module)**: `addRange`, `queryRange`, `removeRange` 동적 인터벌 집합. `TreeMap<Integer, Integer>`로 시작점→끝점 매핑, floor/ceiling로 인접 인터벌 찾아 병합/분할. 정적 정렬 + sweep으로는 매 op마다 O(n) → 비현실적.

### 8.2 "구간 합 쿼리 (sum on range)는?" → Prefix Sum / Fenwick

`sumRange(l, r)`를 빠르게:
- 정적 배열 → prefix sum, O(1) 쿼리.
- 동적 (점 갱신) → Fenwick Tree, O(log n).
- 동적 (구간 갱신 + 점 쿼리) → 차분 배열 + Fenwick.
- 동적 (구간 갱신 + 구간 쿼리) → **Segment Tree + Lazy propagation**.

### 8.3 "Lazy propagation이 뭐죠?"

Segment Tree에서 구간 [l,r]에 같은 값을 더할 때, 매번 모든 leaf를 갱신하면 O(n). Lazy는:
1. 노드에 "이 서브트리에 더해야 할 값"을 lazy 태그로 저장.
2. 실제 자식을 방문할 때만 propagate (push down).
3. op당 O(log n) 유지.

운영 매핑: **rate limiter의 token bucket 갱신**, **scheduling queue의 priority bump**, **trading order book의 가격 레벨 일괄 조정**.

### 8.4 "스트리밍 인터벌이면?"

도착 순서가 무작위인 인터벌 스트림에 대해 "현재까지 합쳐진 인터벌 집합"을 유지하려면:
- `TreeMap<Integer, Integer>` (start→end). 새 인터벌 들어올 때 floor/ceiling로 겹치는 인접 인터벌 찾아 흡수 → O(log n + k), k는 흡수되는 인접 개수 (amortized O(log n)).

### 8.5 "인터벌이 다차원이면?"

2D 인터벌 = 사각형. 겹침 판별 = "x 구간 겹침 AND y 구간 겹침" → 각 차원 독립 처리 가능. 그러나 동적 다차원이면 R-tree, kd-tree 같은 공간 인덱스가 필요. 운영 매핑: **지도 검색 (geospatial)**, **OLAP cube range query**.

### 8.6 "인터벌이 매우 많고 메모리가 빠듯하면?"

- 정수 좌표라면 **좌표 압축** (coordinate compression): 고유 좌표 N'개로 매핑 후 처리.
- **External sort**: 디스크 기반 sweep — 로그 데이터 분석에서 표준.
- **Streaming approximation**: count-min sketch로 동시 진행 개수 근사.

### 8.7 "정확도 vs 근사 trade-off가 있는가?"

스트리밍 환경에서 "현재 동시 진행 세션 수"는 정확히 못 셀 수도 있다 (메모리). HyperLogLog로 cardinality 근사, sliding window로 시간 제한. 데이터독/뉴렐릭 같은 모니터링이 이렇게 동작.

---

## 9. 다른 패턴과의 연결

### 9.1 Sweep Line — 인터벌 ⊂ Sweep Line의 한 사례

Sweep line은 인터벌뿐 아니라 **모든 시간순/공간순 이벤트 처리**의 보편 패러다임:

| 문제 | sweep 이벤트 |
|---|---|
| Meeting Rooms II | (start, +1), (end, -1) |
| LeetCode 218 Skyline | (left, +height), (right, -height) + max-heap |
| LeetCode 391 Perfect Rectangle | 사각형 변의 (x, y_low, y_high) 이벤트 |
| Closest Pair of Points | y좌표 sweep line + ordered set |

**핵심**: 이벤트 정렬 → 좌→우로 훑으며 active 집합 관리. 인터벌은 sweep line의 1D 사례.

### 9.2 Greedy — end 정렬은 activity selection의 표준

LeetCode 435, 452, 단속카메라 — 전부 **activity selection 정리**의 다른 옷. end 정렬 + 첫 끝점 선택 = 최적. 이걸 한 번 증명해두면 모든 변형이 같은 알고리즘으로 풀린다.

**Exchange argument** (증명 스케치): 최적해 OPT가 end가 가장 빠른 활동 a를 안 골랐다고 가정. a를 OPT의 첫 활동과 swap해도 답은 같거나 더 좋음 (a의 end가 더 빠르므로 뒤에 더 많은 자리가 남음). 모순. 따라서 a를 골라도 최적.

### 9.3 Prefix Sum — 인터벌 카운팅과 동치

"각 시점에 진행 중인 회의 수"는 difference array + prefix sum으로도 풀 수 있다:

```
diff[start] += 1
diff[end] -= 1
prefix sum → 각 시점 동시 진행 수
max(prefix) → 최소 회의실
```

좌표가 작으면 O(n + range), 크면 좌표 압축 필요. heap/sweep과 동등.

### 9.4 Heap — 동적 인터벌의 표준 도구

Meeting Rooms II의 min-heap, LeetCode 218 Skyline의 max-heap. **"가장 빨리 끝나는 활성 인터벌"을 O(log n)에 찾는 것**이 heap의 인터벌 유즈케이스.

### 9.5 Two Pointers — 정렬된 두 리스트 결합

LeetCode 986 Interval List Intersections, 그리고 두 정렬된 인터벌 리스트의 합집합/차집합도 같은 패턴. 두 포인터 중 **끝이 빠른 쪽을 전진**.

### 9.6 Binary Search — 인터벌 안에 점이 들어가는지

정렬된 disjoint 인터벌 리스트에서 "값 x를 포함하는 인터벌이 있는가?" → `TreeMap.floorEntry(x)`로 가장 큰 start ≤ x인 인터벌 찾아 end 비교. O(log n). LeetCode 715, 729 (My Calendar I) 등.

---

## 10. 시니어 운영 마스터 관점 — Production 매핑

인터벌 패턴을 백지에서 풀 수 있는 사람은, **운영에서 다음 문제들을 같은 사고로 해결**한다.

### 10.1 Cron schedule overlap detection

수백 개 cron job의 실행 시간 인터벌이 겹쳐 DB 부하 spike가 발생. 각 job을 `[startTime, startTime + estimatedDuration]`로 모델링 → Meeting Rooms II 알고리즘으로 "동시 실행 최대치" 계산 → 그게 DB connection 풀 사이즈 하한.

**진단 코드 시나리오**:
```kotlin
data class JobRun(val name: String, val start: Instant, val end: Instant)

fun peakConcurrency(runs: List<JobRun>): Int {
    val sorted = runs.sortedBy { it.start }
    val heap = PriorityQueue<Instant>()
    var peak = 0
    for (r in sorted) {
        while (heap.isNotEmpty() && heap.peek() <= r.start) heap.poll()
        heap.offer(r.end)
        peak = maxOf(peak, heap.size)
    }
    return peak
}
```

이 함수 하나로 "오늘 새벽 3시에 왜 alert이 떴는지" 답이 나온다.

### 10.2 Distributed lock interval

Redis SETNX 기반 분산 락의 TTL을 짧게 잡으면 만료된 락이 새로 잡혀 충돌. 각 락 보유 기간을 인터벌로 보면, 같은 자원에 대해 **겹침이 발생하는 순간 = 데이터 무결성 위험**. Meeting Rooms I (겹침 판별)을 락 로그에 적용하면 문제 발생 여부를 batch로 검증 가능. Redlock 논문의 핵심 비판도 본질적으로 "인터벌 경계 처리"가 깨질 수 있다는 것.

### 10.3 Calendar / Booking systems

Google Calendar의 "Find a time" 기능 = N명의 busy 인터벌 합집합의 complement (free 인터벌) 계산. Merge Intervals → 합집합 → free = [0, ∞] - busy. 

호텔 예약 시스템에서 "이 객실이 이 기간에 비어있는가?" = 인터벌 겹침 쿼리. 인터벌 수가 수천만 개로 늘어나면 단순 정렬은 부족 → **Segment Tree on time axis** 또는 **Interval Tree**.

### 10.4 SLA window / Maintenance window 계산

운영 SLA: "99.9% 가동률" → 한 달에 허용되는 다운타임 인터벌 총합 계산. 다운타임 인터벌들을 merge → 총 길이가 한도 내인지 검증. PagerDuty/Statuspage가 이걸 한다.

### 10.5 Rate limiter — token bucket 시간 인터벌

token bucket 알고리즘: "지난 N초 동안 발생한 요청 시각들의 sliding window"가 본질적으로 인터벌. 정확한 fixed window는 단순 카운트지만, sliding window는 인터벌 정렬+이진 탐색. Redis ZSET이 이걸 위한 자료구조.

### 10.6 Log analysis — session reconstruction

웹 로그에서 사용자 세션 재구성: 각 click 이벤트를 `[t, t+30s]` 인터벌로 보고 merge하면 "한 세션"이 나옴. Spark의 `sessionWindow` 함수가 정확히 이 알고리즘.

### 10.7 Garbage collection — region marking

G1GC의 region 기반 mark는 메모리 주소 인터벌 단위. 각 region에 살아있는 객체 점유 인터벌을 계산해서 collection 우선순위 결정. CMS/G1 튜닝 시 이 본질을 알면 -XX 옵션의 의미가 다르게 보임.

### 10.8 Stream processing — watermark interval

Apache Flink, Kafka Streams의 watermark는 본질적으로 "이 시각 이전의 이벤트는 모두 도착했다고 본다"는 인터벌 경계. late event handling = open vs closed interval 선택 문제.

---

## 11. 백지 마스터 체크리스트

이 챕터를 마스터했다면 다음을 백지에서 줄줄 풀 수 있다.

- [ ] Interval 문제임을 5초 안에 인지하는 키워드 9개 (start/end 쌍, 병합, 겹침, 회의실, 최소 제거, 화살, 교집합, 삽입, 달력)
- [ ] 정렬 key 결정 규칙 (병합→start, greedy→end, 회의실II→start+heap)
- [ ] 5가지 변형 Java 템플릿 (merge, insert, overlap, rooms, arrows)
- [ ] 동일 5변형 Kotlin 관용 표현 (sortBy, zipWithNext, compareBy)
- [ ] 시간 복잡도가 거의 항상 O(n log n)이고 정렬이 지배적인 이유
- [ ] closed vs half-open interval 경계 처리, `<` vs `<=` 결정
- [ ] sweep line 패러다임이 인터벌·skyline·closest pair에 공통 적용되는 본질
- [ ] activity selection 정리의 exchange argument
- [ ] 동적 인터벌 → TreeMap / Segment Tree / Interval Tree 전환점
- [ ] cron overlap, 분산 락, 캘린더, SLA, rate limiter, session window가 모두 같은 인터벌 사고로 풀린다는 매핑

---

## 12. 핵심 한 줄 요약

> **인터벌 문제는 "정렬 key를 start로 할지 end로 할지" 하나로 90%가 결정된다. 병합·삽입·인접 충돌은 start 정렬, greedy 선택(최대 keep / 최소 제거 / 화살)은 end 정렬, 동시 자원(회의실)은 start 정렬 + min-heap(end). 경계 처리(`>=` vs `>`)는 closed/half-open 정의에 따라 결정되며, 면접관이 묻기 전에 명시적으로 확인하는 것이 마스터의 표시다.**
