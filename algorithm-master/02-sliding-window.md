# 02. Sliding Window (슬라이딩 윈도우)

> "윈도우를 움직이면 되는 거 아냐?" 라고 답하면 입문자. 마스터는 (1) 윈도우의 **invariant**를 먼저 정의하고, (2) **언제 확장하고 언제 수축**할지 한 줄로 말하며, (3) `right` 인덱스가 N번 + `left` 인덱스가 N번 = **amortized O(n)** 임을 증명한다. 그리고 production에서 rate limiter sliding window, log streaming 최근 N초 통계, 네트워크 TCP congestion window, observability 이상치 탐지가 모두 같은 패턴임을 본다.
>
> 이 문서는 옵션·문법 외우기 대신 본질·왜·연결·운영 진단만 다룬다. 단, 라이브 코딩 테스트에서 그대로 통과하는 Java/Kotlin 템플릿은 포함한다.

---

## 0. 인지 신호 — 이 키워드가 보이면 sliding window를 의심하라

| 한국어 문제 표현 | 영어 키워드 | 의미 |
|---|---|---|
| "연속된 부분 배열" / "연속된 부분 문자열" | "contiguous subarray", "substring" | 인덱스가 연속 — 윈도우의 본질 |
| "길이 K짜리 부분 배열의 최대·최소·합·평균" | "fixed-size window of size K" | 고정 윈도우 (sum trick) |
| "조건을 만족하는 가장 긴/짧은 부분 배열" | "longest/shortest subarray with property" | 가변 윈도우 (expand-shrink) |
| "정확히 K개의 서로 다른 문자" | "exactly K distinct" | atMost(K) − atMost(K−1) 변환 |
| "최대 K개까지 교체/대체 가능" | "at most K replacements" | 가변 윈도우 + 카운트 맵 |
| "윈도우 안에서의 최댓값/최솟값" | "max/min in sliding window" | monotonic deque 변형 |
| "스트리밍에서 최근 K개" / "최근 N초" | "moving average", "recent N seconds" | 시간축 윈도우, 같은 원리 |
| "anagram, permutation, 순열" | "anagram/permutation in string" | 고정 길이 + 카운트 매칭 |

**부정 신호** — sliding window가 *아닌* 패턴:
- "정렬된 배열에서 합 = target" → Two Pointers (양 끝에서 좁혀오기)
- "구간 합 쿼리가 여러 번" → Prefix Sum
- "비연속 부분 수열" → DP / Greedy / Subsequence
- "구간을 정렬해서 병합" → Intervals

> 핵심 판정: **"연속(contiguous)" + "어떤 조건의 최대·최소·개수"** 가 동시에 나오면 90%는 sliding window.

---

## 1. 백지 그리기 — 4가지 윈도우 형태

### 1.1 고정 윈도우 (Fixed-Size)

```
배열 nums = [1, 3, -1, -3, 5, 3, 6, 7],  K = 3

step 0:  [1  3  -1] -3   5   3   6   7      sum = 3
step 1:   1 [3  -1  -3]  5   3   6   7      sum = -1   (− 1, + -3)
step 2:   1  3 [-1  -3   5]  3   6   7      sum = 1    (− 3, + 5)
step 3:   1  3  -1 [-3   5   3]  6   7      sum = 5
step 4:   1  3  -1  -3  [5   3   6]  7      sum = 14
step 5:   1  3  -1  -3   5  [3   6   7]     sum = 16

규칙:  right 한 칸 전진 → 새 원소 더함 → left 한 칸 전진 → 빠지는 원소 뺌
       O(1) 증분 갱신.  K개 다시 세지 않는다 — 이게 핵심.
```

핵심 깨달음: **고정 윈도우는 "재계산" 아니라 "증분 (delta) 갱신"이다.** `new = old + nums[right] - nums[left]`. 라이브 코딩에서 이걸 모르고 매번 K개 sum 다시 돌리면 O(N·K) → TLE.

### 1.2 가변 윈도우 (Variable-Size, Expand-Shrink)

```
가장 일반적 형태:  "조건 P를 만족하는 가장 긴/짧은 연속 부분 배열"

   ┌─────────────────────── while (right < n) ─────────────────────┐
   │                                                                │
   │   1. window에 nums[right] 추가  (확장)                          │
   │   2. while (window가 invariant 위반) {                          │
   │         nums[left] 제거                                         │
   │         left++                                                  │
   │      }                                                          │
   │   3. 이제 window는 invariant 만족 → 답 갱신                     │
   │   4. right++                                                    │
   │                                                                │
   └────────────────────────────────────────────────────────────────┘

예:  "중복 없는 가장 긴 부분 문자열"  s = "abcabcbb"

right=0  "a"        valid    best=1
right=1  "ab"       valid    best=2
right=2  "abc"      valid    best=3
right=3  "abca"     dup 'a'  → shrink:  left=1  "bca"   valid   best=3
right=4  "bcab"     dup 'b'  → shrink:  left=2  "cab"   valid   best=3
right=5  "cabc"     dup 'c'  → shrink:  left=3  "abc"   valid   best=3
right=6  "abcb"     dup 'b'  → shrink:  left=5  "cb"    valid   best=3
right=7  "cbb"      dup 'b'  → shrink:  left=6  "bb"  → left=7  "b"
                                       valid                    best=3
답: 3   ("abc")
```

여기서 핵심은 **invariant** — 이 윈도우 안에서 항상 참이어야 하는 성질. "중복 없음" / "sum ≤ target" / "distinct ≤ K" 같은 것.

### 1.3 카운트 맵 윈도우 (Count Map / Frequency Window)

```
"Minimum Window Substring":   s = "ADOBECODEBANC"   t = "ABC"

need:  {A:1, B:1, C:1}        formed=0   need.size()=3

right 전진 → 카운트 증가 → formed 갱신
left  전진 → 카운트 감소 → formed 감소 가능

   s = A D O B E C O D E B A N C
       ^               ^
       left            right

   window count = {A:1, D:1, O:1, B:1, E:1, C:1}
   formed = 3  (A·B·C 모두 need 만큼)
        → invariant 만족, shrink 시도
        → 'A' 제거 → formed = 2  (A가 부족)
        → shrink 중단, right 다시 전진

   최종:  "BANC"  (length 4)
```

**formed 카운터의 정체**: "현재 window가 필요 조건을 몇 종류 만족하는가". 이걸 안 쓰면 매 step마다 `for ch in need: if windowCount[ch] < need[ch] ...` 도는 O(|Σ|) — 전체 O(N·|Σ|). formed로는 O(N).

### 1.4 Monotonic Deque 윈도우 (Sliding Window Maximum)

```
"K개 연속 부분 배열의 최댓값" — nums = [1, 3, -1, -3, 5, 3, 6, 7], K = 3

핵심:  deque에 인덱스를 저장.  값이 감소(non-increasing)하도록 유지.
       front = 현재 window의 최댓값 인덱스.

right=0  nums[0]=1   deque = [0]                front값 = 1
right=1  nums[1]=3   1<3, pop 0 → deque = [1]   front값 = 3
right=2  nums[2]=-1  -1<3, deque = [1, 2]       front값 = 3   → window [1,3,-1] max=3
right=3  nums[3]=-3  -3<-1, deque = [1, 2, 3]
                     left=1, front=1 still in window → max=3 → [3,-1,-3] max=3
right=4  nums[4]=5   pop -3, -1, 3 → deque = [4]    → [-1,-3,5] max=5
right=5  nums[5]=3   3<5, deque = [4, 5]            → [-3,5,3]  max=5
right=6  nums[6]=6   pop 3, deque = [4, 6]
                     left=4, front=4 still in window
                     wait — left = right - K + 1 = 4 → front=4 OK   max=6
                     → window [5,3,6] max=6
right=7  nums[7]=7   pop 6, 4 → deque = [7]         → [3,6,7] max=7

답: [3, 3, 5, 5, 6, 7]

deque invariant:
   (1) 인덱스가 단조 증가  (왼쪽일수록 작은 i)
   (2) 값이 단조 감소     (왼쪽일수록 큰 nums[i])
   (3) front 인덱스가 [left, right] 범위 — 벗어나면 pollFirst
```

여기서 **각 인덱스는 deque에 한 번 들어가고 한 번 나간다** — 총 push/pop 2N → amortized O(n). 이게 monotonic deque가 sliding window의 max/min을 O(n)에 푸는 마법.

---

## 2. 직관과 정의

### 2.1 한 줄 비유

> **"문서 위에 자(ruler)를 올려놓고, 오른쪽으로 끌면서 가끔 왼쪽도 같이 끄는 행위. 자 안에 들어온 내용만 본다."**

- 자가 **고정 길이** → 고정 윈도우 (fixed)
- 자가 **늘었다 줄었다** → 가변 윈도우 (variable)
- 자 안의 **빈도수**를 추적 → 카운트 맵 윈도우
- 자 안의 **최댓값/최솟값**을 추적 → monotonic deque

### 2.2 정확한 정의

배열/문자열 `A[0..n-1]` 위에서 두 포인터 `left ≤ right`로 정의되는 **연속 구간** `A[left..right]`. 이 구간을 **window** 라 한다. 다음을 유지하며 right를 0부터 n-1까지 한 번 훑는다:

1. **확장 (expand)**: `A[right]`를 window에 추가, 보조 자료구조(sum, count map, deque) 갱신.
2. **수축 (shrink)**: window가 invariant를 위반하면 `A[left]`를 제거하고 `left++`. 위반이 사라질 때까지 반복.
3. **답 갱신**: window가 invariant를 만족하는 시점에 답 후보를 갱신.
4. **전진**: `right++`.

amortized 분석: left와 right는 각각 0에서 n-1까지 단조 증가만 한다 → 총 이동 2n번 → **O(n)**.

### 2.3 Two Pointers와의 차이

| | Two Pointers | Sliding Window |
|---|---|---|
| 시작 위치 | 양 끝 (left=0, right=n-1) 또는 같은 출발 | 같은 출발 (left=right=0) |
| 이동 방향 | 가운데로 수렴 (또는 fast/slow) | 둘 다 오른쪽으로만 |
| 대상 | 보통 정렬된 배열의 쌍 (sum, pair) | 연속 부분 배열/문자열 |
| 답의 형태 | 인덱스 쌍, boolean | 연속 구간의 길이/합/개수 |
| 자료구조 | 보통 없음 | sum, count map, deque |

**경계가 모호한 경우**: "정렬된 배열에서 sum=target 쌍 찾기"는 Two Pointers, "비정렬 배열에서 sum=target인 *연속* 부분 배열"은 Sliding Window. 키워드는 **"연속"**.

### 2.4 Invariant — sliding window의 진짜 본질

문제마다 invariant가 다르고, 이걸 한 줄로 못 쓰면 코드도 못 쓴다.

| 문제 | invariant |
|---|---|
| Longest Substring Without Repeating | "window 안 문자 모두 distinct" |
| Minimum Size Subarray Sum ≥ target | "window sum ≥ target" (수축 가능 조건) |
| Longest Substring with At Most K Distinct | "distinct count ≤ K" |
| Longest Repeating Char Replacement | "windowLen − maxFreq ≤ K" |
| Permutation in String | "window 길이 = |t|" + "count 일치" |
| Sliding Window Maximum | "window 길이 = K" + "deque 단조 감소" |

invariant를 먼저 종이에 쓰고 코드를 시작하라. 라이브 코딩에서 면접관이 가장 먼저 묻는 게 이거다.

---

## 3. Java 템플릿

### 3.1 고정 윈도우 (Fixed-Size Sum/Avg/Max)

```java
public double[] fixedWindow(int[] nums, int k) {
    int n = nums.length;
    double[] result = new double[n - k + 1];
    long sum = 0;
    for (int i = 0; i < k; i++) sum += nums[i];   // 초기 윈도우
    result[0] = (double) sum / k;
    for (int right = k; right < n; right++) {
        sum += nums[right] - nums[right - k];     // 증분 갱신: O(1)
        result[right - k + 1] = (double) sum / k;
    }
    return result;
}
```

**핵심**: 윈도우를 한 칸 옮길 때 새로 들어온 것을 더하고 빠진 것을 뺀다. **K개를 매번 더하지 마라**.

오버플로우 주의: `sum`은 `long`. `int`는 N=10^5 × 값 10^9이면 곧 넘는다.

### 3.2 가변 윈도우 (Variable-Size, while-shrink)

라이브 코딩에서 가장 자주 쓰는 boilerplate. 한 번 외워두면 변형 가능하다.

```java
public int variableWindow(int[] nums, /* params */) {
    int n = nums.length;
    int left = 0;
    int best = 0;        // 또는 Integer.MAX_VALUE (최소 찾기)
    // 보조 자료구조: sum / Map / Set / int[]
    long sum = 0;

    for (int right = 0; right < n; right++) {
        // 1. expand: nums[right]를 window에 추가
        sum += nums[right];

        // 2. shrink: invariant 위반 시 left 전진
        while (/* invariant 위반 */ sum > TARGET) {
            sum -= nums[left];
            left++;
        }

        // 3. update answer (invariant 만족 상태)
        best = Math.max(best, right - left + 1);
    }
    return best;
}
```

**관용**: `while` (not `if`) — 한 번에 여러 칸 줄여야 할 수 있음. `if`로 쓰면 sneaky 버그.

**길이**: `right - left + 1` (양 끝 포함).

### 3.3 카운트 HashMap 윈도우

```java
public int longestKDistinct(String s, int k) {
    Map<Character, Integer> count = new HashMap<>();
    int left = 0, best = 0;
    for (int right = 0; right < s.length(); right++) {
        char c = s.charAt(right);
        count.merge(c, 1, Integer::sum);
        while (count.size() > k) {
            char l = s.charAt(left);
            if (count.merge(l, -1, Integer::sum) == 0) count.remove(l);
            left++;
        }
        best = Math.max(best, right - left + 1);
    }
    return best;
}
```

**관용 1**: `count.merge(c, 1, Integer::sum)` — 없으면 1, 있으면 +1. JDK 8+.
**관용 2**: 0이 되면 반드시 `remove` — 안 그러면 `count.size()`가 거짓 보고.
**관용 3**: ASCII만이면 `int[26]` 또는 `int[128]` — HashMap보다 10배 빠르다. 라이브 코딩에서 시간 빠듯하면 char→int 배열 우선.

### 3.4 카운트 매칭 윈도우 (Minimum Window / Anagram)

formed 카운터 패턴 — Minimum Window Substring의 정석.

```java
public String minWindow(String s, String t) {
    if (s.length() < t.length()) return "";
    Map<Character, Integer> need = new HashMap<>();
    for (char c : t.toCharArray()) need.merge(c, 1, Integer::sum);

    int required = need.size();
    int formed = 0;
    Map<Character, Integer> window = new HashMap<>();

    int left = 0, bestLen = Integer.MAX_VALUE, bestL = 0;

    for (int right = 0; right < s.length(); right++) {
        char c = s.charAt(right);
        window.merge(c, 1, Integer::sum);
        if (need.containsKey(c) && window.get(c).intValue() == need.get(c).intValue()) {
            formed++;
        }

        while (formed == required) {
            if (right - left + 1 < bestLen) {
                bestLen = right - left + 1;
                bestL = left;
            }
            char l = s.charAt(left);
            int cnt = window.merge(l, -1, Integer::sum);
            if (need.containsKey(l) && cnt < need.get(l).intValue()) {
                formed--;
            }
            left++;
        }
    }
    return bestLen == Integer.MAX_VALUE ? "" : s.substring(bestL, bestL + bestLen);
}
```

**함정**: `window.get(c).intValue() == need.get(c).intValue()` — `Integer` 비교는 `==` 쓰면 `-128~127` 캐시 밖에서 false. 반드시 `.intValue()` 또는 `.equals()`.

### 3.5 Monotonic Deque (Sliding Window Maximum)

```java
public int[] maxSlidingWindow(int[] nums, int k) {
    int n = nums.length;
    int[] result = new int[n - k + 1];
    Deque<Integer> dq = new ArrayDeque<>();   // 인덱스 저장
    for (int right = 0; right < n; right++) {
        // 1. 범위 벗어난 front 제거
        while (!dq.isEmpty() && dq.peekFirst() <= right - k) {
            dq.pollFirst();
        }
        // 2. 단조 감소 유지: 뒤에서 작은 값 제거
        while (!dq.isEmpty() && nums[dq.peekLast()] <= nums[right]) {
            dq.pollLast();
        }
        dq.offerLast(right);
        // 3. window 형성됐으면 답 기록
        if (right >= k - 1) {
            result[right - k + 1] = nums[dq.peekFirst()];
        }
    }
    return result;
}
```

**왜 인덱스를 저장?** 값만 저장하면 "이게 window 안인지" 판단 불가. 인덱스가 있어야 `i <= right - k`로 expiration 판정.

**최솟값**이 필요하면 `<=`를 `>=`로 뒤집고, 변수명 적당히 바꾸면 그대로 작동.

---

## 4. Kotlin 템플릿

### 4.1 고정 윈도우

```kotlin
fun fixedWindow(nums: IntArray, k: Int): DoubleArray {
    val n = nums.size
    val result = DoubleArray(n - k + 1)
    var sum = 0L
    for (i in 0 until k) sum += nums[i]
    result[0] = sum.toDouble() / k
    for (right in k until n) {
        sum += nums[right] - nums[right - k]
        result[right - k + 1] = sum.toDouble() / k
    }
    return result
}
```

### 4.2 가변 윈도우

```kotlin
fun variableWindow(nums: IntArray, target: Long): Int {
    var left = 0
    var best = 0
    var sum = 0L
    for (right in nums.indices) {
        sum += nums[right]
        while (sum > target) {
            sum -= nums[left]
            left++
        }
        best = maxOf(best, right - left + 1)
    }
    return best
}
```

Kotlin의 `nums.indices`는 `0 until nums.size`와 동일. `maxOf`는 `Math.max` 대체.

### 4.3 카운트 맵 윈도우 (Longest Substring Without Repeating)

```kotlin
fun lengthOfLongestSubstring(s: String): Int {
    val count = IntArray(128)        // ASCII면 충분
    var left = 0
    var best = 0
    for (right in s.indices) {
        val c = s[right].code
        count[c]++
        while (count[c] > 1) {
            count[s[left].code]--
            left++
        }
        best = maxOf(best, right - left + 1)
    }
    return best
}
```

`Char.code`는 Kotlin 1.5+. 이전 버전은 `s[right].toInt()`.

### 4.4 카운트 매칭 (Minimum Window Substring)

```kotlin
fun minWindow(s: String, t: String): String {
    if (s.length < t.length) return ""
    val need = IntArray(128)
    var required = 0
    for (c in t) {
        if (need[c.code]++ == 0) required++
    }
    val window = IntArray(128)
    var formed = 0
    var left = 0
    var bestLen = Int.MAX_VALUE
    var bestL = 0

    for (right in s.indices) {
        val c = s[right].code
        window[c]++
        if (need[c] > 0 && window[c] == need[c]) formed++

        while (formed == required) {
            if (right - left + 1 < bestLen) {
                bestLen = right - left + 1
                bestL = left
            }
            val l = s[left].code
            window[l]--
            if (need[l] > 0 && window[l] < need[l]) formed--
            left++
        }
    }
    return if (bestLen == Int.MAX_VALUE) "" else s.substring(bestL, bestL + bestLen)
}
```

### 4.5 Monotonic Deque

```kotlin
fun maxSlidingWindow(nums: IntArray, k: Int): IntArray {
    val n = nums.size
    val result = IntArray(n - k + 1)
    val dq = ArrayDeque<Int>()
    for (right in 0 until n) {
        while (dq.isNotEmpty() && dq.first() <= right - k) dq.removeFirst()
        while (dq.isNotEmpty() && nums[dq.last()] <= nums[right]) dq.removeLast()
        dq.addLast(right)
        if (right >= k - 1) result[right - k + 1] = nums[dq.first()]
    }
    return result
}
```

Kotlin `ArrayDeque`는 `kotlin.collections.ArrayDeque` (1.4+). Java의 `java.util.ArrayDeque`와 별개 — Kotlin 쪽이 API가 깔끔(`first`/`last`/`removeFirst`/`removeLast`).

---

## 5. 시간/공간 복잡도

### 5.1 왜 amortized O(n)인가

```
for (right in 0 until n):
    expand                          # O(1)
    while (invariant 위반):
        shrink                      # 각 shrink는 O(1)
        left++
    update                          # O(1)
    right++

left와 right는 각각 0에서 n-1까지 단조 증가.
총 expand 횟수 = n  (right 한 번씩)
총 shrink 횟수 ≤ n  (left가 n까지 가는 데 최대 n번)

내부 while이 무서워 보이지만,
"평균(amortized)" 비용은 op당 (n+n)/n = 2 = O(1).
전체 시간: O(n).
```

**유사 사례** — dynamic array의 amortized 분석. 안에 loop가 보여도 총 iteration이 N으로 묶이면 amortized O(1)/op.

라이브 코딩에서 면접관이 "while 안에 또 loop 있는데 어떻게 O(n)?" 물으면 위 분석을 정확히 말해야 한다. 외워라:

> **"left와 right 둘 다 0에서 n까지 단조 증가만 한다. 각자 최대 n번 이동하므로 총 2n step, amortized O(n)."**

### 5.2 자료구조별 비용

| 자료구조 | expand/shrink | 추가 공간 |
|---|---|---|
| 단순 sum (long) | O(1) | O(1) |
| `int[128]` count | O(1) | O(1) (Σ 상수) |
| `HashMap<K, Integer>` | 평균 O(1), 최악 O(log N) (JDK 8 tree) | O(distinct) |
| `Deque<Integer>` (monotonic) | amortized O(1) | O(K) |
| `TreeMap` (정렬 카운트) | O(log N) | O(distinct) |

라이브 코딩에서 ASCII 문자열이면 무조건 `int[128]` (또는 `int[26]`). HashMap의 box/unbox + hash 충돌 + treeify로 P99에서 느려진다.

### 5.3 공간 복잡도

- 보통 O(min(N, |Σ|)) 또는 O(K).
- 결과 배열까지 합치면 O(n - k + 1).

---

## 6. 대표 문제 (8개 풀이)

### 문제 1. LeetCode 3 — Longest Substring Without Repeating Characters

> 문자열 `s`가 주어진다. 중복 문자가 없는 가장 긴 부분 문자열의 길이를 반환.
> 예: `s = "abcabcbb"` → `3` ("abc")

**접근**: 가변 윈도우 + count 배열. invariant = "window 안 모든 문자 빈도 ≤ 1". `count[c] > 1`이면 shrink.

**Java 풀이**:

```java
class Solution {
    public int lengthOfLongestSubstring(String s) {
        int[] count = new int[128];
        int left = 0, best = 0;
        for (int right = 0; right < s.length(); right++) {
            char c = s.charAt(right);
            count[c]++;
            while (count[c] > 1) {
                count[s.charAt(left)]--;
                left++;
            }
            best = Math.max(best, right - left + 1);
        }
        return best;
    }
}
```

**Kotlin 풀이**:

```kotlin
class Solution {
    fun lengthOfLongestSubstring(s: String): Int {
        val count = IntArray(128)
        var left = 0
        var best = 0
        for (right in s.indices) {
            val c = s[right].code
            count[c]++
            while (count[c] > 1) {
                count[s[left].code]--
                left++
            }
            best = maxOf(best, right - left + 1)
        }
        return best
    }
}
```

**복잡도**: 시간 O(n), 공간 O(|Σ|) = O(128).

**함정**:
- 유니코드 한글/이모지면 `int[128]` 부족 → `HashMap<Character, Integer>` 또는 `int[0x10000]`.
- `count[c] > 1` 체크 후 shrink — `==` 으로 쓰면 multi-dup에서 무한 루프 가능 (사실은 안 그러지만 정신적으로 `> 1`이 안전).
- O(n²) 풀이 (모든 부분 문자열 brute force)도 정답이지만 n=5×10^4 한계.

### 문제 2. LeetCode 76 — Minimum Window Substring

> 문자열 `s`와 `t`. `s`에서 `t`의 모든 문자(중복 포함)를 포함하는 **가장 짧은** 부분 문자열 반환. 없으면 `""`.
> 예: `s = "ADOBECODEBANC"`, `t = "ABC"` → `"BANC"`

**접근**: 카운트 매칭 윈도우 + `formed` 카운터. invariant = "window가 t를 모두 cover". cover하면 shrink 시도.

**Java 풀이**:

```java
class Solution {
    public String minWindow(String s, String t) {
        if (s.length() < t.length()) return "";
        int[] need = new int[128];
        int required = 0;
        for (char c : t.toCharArray()) {
            if (need[c]++ == 0) required++;
        }
        int[] window = new int[128];
        int formed = 0, left = 0;
        int bestLen = Integer.MAX_VALUE, bestL = 0;
        for (int right = 0; right < s.length(); right++) {
            char c = s.charAt(right);
            window[c]++;
            if (need[c] > 0 && window[c] == need[c]) formed++;
            while (formed == required) {
                if (right - left + 1 < bestLen) {
                    bestLen = right - left + 1;
                    bestL = left;
                }
                char l = s.charAt(left);
                window[l]--;
                if (need[l] > 0 && window[l] < need[l]) formed--;
                left++;
            }
        }
        return bestLen == Integer.MAX_VALUE ? "" : s.substring(bestL, bestL + bestLen);
    }
}
```

**Kotlin 풀이** (§4.4 참조).

**복잡도**: 시간 O(|s| + |t|), 공간 O(|Σ|).

**함정**:
- t에 중복 문자 (`t = "AABC"`) → `need[A] = 2`. window count가 2가 될 때만 formed++.
- formed 증감 시점: `window[c] == need[c]`로 정확히 같아질 때만 ++. 그 이상 늘어도 ++ 금지 (이중 카운트).
- 비ASCII 입력 가능성 — LeetCode 76은 ASCII만 보장하지만 변형 문제에선 주의.

### 문제 3. LeetCode 209 — Minimum Size Subarray Sum

> 양의 정수 배열 `nums`, 양의 정수 `target`. `sum ≥ target`인 가장 **짧은** 연속 부분 배열 길이. 없으면 0.
> 예: `nums = [2,3,1,2,4,3]`, `target = 7` → `2` ([4,3])

**접근**: 가변 윈도우. invariant = `sum < target`. 위반(`sum ≥ target`)이면 답 후보 갱신하며 shrink.

**Java 풀이**:

```java
class Solution {
    public int minSubArrayLen(int target, int[] nums) {
        int left = 0;
        long sum = 0;
        int best = Integer.MAX_VALUE;
        for (int right = 0; right < nums.length; right++) {
            sum += nums[right];
            while (sum >= target) {
                best = Math.min(best, right - left + 1);
                sum -= nums[left];
                left++;
            }
        }
        return best == Integer.MAX_VALUE ? 0 : best;
    }
}
```

**Kotlin 풀이**:

```kotlin
class Solution {
    fun minSubArrayLen(target: Int, nums: IntArray): Int {
        var left = 0
        var sum = 0L
        var best = Int.MAX_VALUE
        for (right in nums.indices) {
            sum += nums[right]
            while (sum >= target) {
                best = minOf(best, right - left + 1)
                sum -= nums[left]
                left++
            }
        }
        return if (best == Int.MAX_VALUE) 0 else best
    }
}
```

**복잡도**: 시간 O(n), 공간 O(1).

**함정**:
- 음수가 포함되면 sliding window **불가** — sum이 단조 증가가 아니라서 shrink 결정 못함. 음수면 prefix sum + monotonic deque 또는 prefix sum + TreeMap.
- `sum`은 `long`. nums[i] ≤ 10^4, n ≤ 10^5 → 최대 10^9이라 int 경계지만 변형 문제에서 위험.
- "≥ target" vs "= target" — sliding window가 깔끔히 풀리는 건 ≥/≤ 단조 조건. 정확히 같은 건 prefix sum + HashMap 패턴.

### 문제 4. LeetCode 567 — Permutation in String

> 문자열 `s1`, `s2`. `s2`가 `s1`의 어떤 순열(permutation)을 부분 문자열로 포함하면 true.
> 예: `s1 = "ab"`, `s2 = "eidbaooo"` → `true` ("ba")

**접근**: 고정 길이 (`|s1|`) 윈도우. invariant = "window 카운트 == s1 카운트". 한 칸 이동마다 두 카운트 비교 O(26).

**Java 풀이**:

```java
class Solution {
    public boolean checkInclusion(String s1, String s2) {
        int n1 = s1.length(), n2 = s2.length();
        if (n1 > n2) return false;
        int[] need = new int[26];
        int[] window = new int[26];
        for (int i = 0; i < n1; i++) {
            need[s1.charAt(i) - 'a']++;
            window[s2.charAt(i) - 'a']++;
        }
        if (Arrays.equals(need, window)) return true;
        for (int right = n1; right < n2; right++) {
            window[s2.charAt(right) - 'a']++;
            window[s2.charAt(right - n1) - 'a']--;
            if (Arrays.equals(need, window)) return true;
        }
        return false;
    }
}
```

**Kotlin 풀이**:

```kotlin
class Solution {
    fun checkInclusion(s1: String, s2: String): Boolean {
        val n1 = s1.length
        val n2 = s2.length
        if (n1 > n2) return false
        val need = IntArray(26)
        val window = IntArray(26)
        for (i in 0 until n1) {
            need[s1[i] - 'a']++
            window[s2[i] - 'a']++
        }
        if (need.contentEquals(window)) return true
        for (right in n1 until n2) {
            window[s2[right] - 'a']++
            window[s2[right - n1] - 'a']--
            if (need.contentEquals(window)) return true
        }
        return false
    }
}
```

**복잡도**: 시간 O(|s2| · 26) = O(|s2|), 공간 O(26).

**함정**:
- `Arrays.equals`는 매번 26번 비교 — 진짜 O(1) 원하면 `matches` 카운터로 26번 → 1번 비교로 줄일 수 있음 (optimal). 라이브 코딩에선 위 코드면 충분.
- "어떤 순열을 부분 문자열로" — 즉 anagram. 헷갈리지 마라.

### 문제 5. LeetCode 424 — Longest Repeating Character Replacement

> 문자열 `s`와 정수 `k`. `s`의 문자 최대 `k`개를 다른 문자로 교체하여 만들 수 있는 가장 긴 "동일 문자 연속 부분 문자열" 길이.
> 예: `s = "AABABBA"`, `k = 1` → `4` ("AABA" → "AAAA" 가능)

**접근**: 가변 윈도우. invariant = `windowLen − maxFreq ≤ k` (즉, "윈도우 내 최빈 문자 빼고 나머지가 k 이하"). 위반이면 shrink.

```
windowLen − maxFreq = 윈도우 안에서 "교체해야 하는 문자 수"
이게 k 이하면 invariant 만족.
```

**Java 풀이**:

```java
class Solution {
    public int characterReplacement(String s, int k) {
        int[] count = new int[26];
        int left = 0, maxFreq = 0, best = 0;
        for (int right = 0; right < s.length(); right++) {
            count[s.charAt(right) - 'A']++;
            maxFreq = Math.max(maxFreq, count[s.charAt(right) - 'A']);
            while (right - left + 1 - maxFreq > k) {
                count[s.charAt(left) - 'A']--;
                left++;
            }
            best = Math.max(best, right - left + 1);
        }
        return best;
    }
}
```

**Kotlin 풀이**:

```kotlin
class Solution {
    fun characterReplacement(s: String, k: Int): Int {
        val count = IntArray(26)
        var left = 0
        var maxFreq = 0
        var best = 0
        for (right in s.indices) {
            val idx = s[right] - 'A'
            count[idx]++
            maxFreq = maxOf(maxFreq, count[idx])
            while (right - left + 1 - maxFreq > k) {
                count[s[left] - 'A']--
                left++
            }
            best = maxOf(best, right - left + 1)
        }
        return best
    }
}
```

**복잡도**: 시간 O(n), 공간 O(26).

**함정 (유명)**:
- `maxFreq`를 shrink 시 **재계산하지 않는다**. 직관적으로는 "left 줄였으니 maxFreq도 줄겠지" 싶지만 안 줄여도 OK — 어차피 답은 best이고, `best`가 갱신되려면 `maxFreq`가 *증가*해야만 한다. 즉 maxFreq가 stale해도 답에 영향 없음. 이게 이 문제의 트릭.
- 면접관이 "maxFreq 갱신 안 해도 돼요?" 물으면 위 논거 정확히 말할 것.

### 문제 6. LeetCode 239 — Sliding Window Maximum

> 배열 `nums`, 크기 `k`. 모든 길이 `k` 부분 배열의 최댓값을 배열로 반환.
> 예: `nums = [1,3,-1,-3,5,3,6,7]`, `k = 3` → `[3,3,5,5,6,7]`

**접근**: monotonic deque (값 단조 감소). §3.5 참조.

**Java 풀이** (§3.5 그대로):

```java
class Solution {
    public int[] maxSlidingWindow(int[] nums, int k) {
        int n = nums.length;
        int[] result = new int[n - k + 1];
        Deque<Integer> dq = new ArrayDeque<>();
        for (int right = 0; right < n; right++) {
            while (!dq.isEmpty() && dq.peekFirst() <= right - k) dq.pollFirst();
            while (!dq.isEmpty() && nums[dq.peekLast()] <= nums[right]) dq.pollLast();
            dq.offerLast(right);
            if (right >= k - 1) result[right - k + 1] = nums[dq.peekFirst()];
        }
        return result;
    }
}
```

**Kotlin 풀이** (§4.5 그대로):

```kotlin
class Solution {
    fun maxSlidingWindow(nums: IntArray, k: Int): IntArray {
        val n = nums.size
        val result = IntArray(n - k + 1)
        val dq = ArrayDeque<Int>()
        for (right in 0 until n) {
            while (dq.isNotEmpty() && dq.first() <= right - k) dq.removeFirst()
            while (dq.isNotEmpty() && nums[dq.last()] <= nums[right]) dq.removeLast()
            dq.addLast(right)
            if (right >= k - 1) result[right - k + 1] = nums[dq.first()]
        }
        return result
    }
}
```

**복잡도**: 시간 O(n) (각 인덱스 push/pop 한 번씩), 공간 O(k).

**함정**:
- **값이 아니라 인덱스 저장**. expiration 판정에 인덱스 필요.
- `<=` vs `<` — `<=`로 쓰면 같은 값 중 가장 최근 것만 남음, OK. `<`로 쓰면 같은 값이 stack에 쌓임, 메모리 낭비지만 정답은 동일.
- `java.util.LinkedList`도 Deque이지만 `ArrayDeque`가 2~3배 빠름 (cache locality).

### 문제 7. LeetCode 438 — Find All Anagrams in a String

> `s`, `p`. `s`에서 `p`의 anagram에 해당하는 모든 시작 인덱스 리스트 반환.
> 예: `s = "cbaebabacd"`, `p = "abc"` → `[0, 6]`

**접근**: 567과 동일. 고정 길이 `|p|` 윈도우. count 일치 시점의 left 기록.

**Java 풀이**:

```java
class Solution {
    public List<Integer> findAnagrams(String s, String p) {
        List<Integer> result = new ArrayList<>();
        int ns = s.length(), np = p.length();
        if (ns < np) return result;
        int[] need = new int[26];
        int[] window = new int[26];
        for (int i = 0; i < np; i++) {
            need[p.charAt(i) - 'a']++;
            window[s.charAt(i) - 'a']++;
        }
        if (Arrays.equals(need, window)) result.add(0);
        for (int right = np; right < ns; right++) {
            window[s.charAt(right) - 'a']++;
            window[s.charAt(right - np) - 'a']--;
            if (Arrays.equals(need, window)) result.add(right - np + 1);
        }
        return result;
    }
}
```

**Kotlin 풀이**:

```kotlin
class Solution {
    fun findAnagrams(s: String, p: String): List<Int> {
        val result = mutableListOf<Int>()
        val ns = s.length
        val np = p.length
        if (ns < np) return result
        val need = IntArray(26)
        val window = IntArray(26)
        for (i in 0 until np) {
            need[p[i] - 'a']++
            window[s[i] - 'a']++
        }
        if (need.contentEquals(window)) result.add(0)
        for (right in np until ns) {
            window[s[right] - 'a']++
            window[s[right - np] - 'a']--
            if (need.contentEquals(window)) result.add(right - np + 1)
        }
        return result
    }
}
```

**복잡도**: 시간 O(|s| · 26), 공간 O(26 + 결과 개수).

**함정**:
- 시작 인덱스 = `right - np + 1`. off-by-one 빈출.
- 567과 차이: 567은 true/false 하나만, 438은 모든 위치 모음.

### 문제 8. Programmers — 보석 쇼핑 (Lv.3)

> 진열대 보석 배열에서 **모든 종류**의 보석을 포함하는 가장 짧은 연속 구간 `[start, end]` (1-indexed) 반환. 동일 길이면 start 작은 것.
> 예: `["DIA","RUBY","RUBY","DIA","DIA","EMERALD","SAPPHIRE","DIA"]` → `[3, 7]`

**접근**: 카운트 매칭. 전체 distinct 종류 수 K. K개 모두 cover한 시점에 shrink하며 최단 갱신.

**Java 풀이**:

```java
import java.util.*;

class Solution {
    public int[] solution(String[] gems) {
        Set<String> kinds = new HashSet<>(Arrays.asList(gems));
        int required = kinds.size();
        Map<String, Integer> window = new HashMap<>();
        int formed = 0, left = 0;
        int bestLen = Integer.MAX_VALUE, bestL = 0, bestR = 0;
        for (int right = 0; right < gems.length; right++) {
            String g = gems[right];
            window.merge(g, 1, Integer::sum);
            if (window.get(g) == 1) formed++;
            while (formed == required) {
                if (right - left + 1 < bestLen) {
                    bestLen = right - left + 1;
                    bestL = left;
                    bestR = right;
                }
                String l = gems[left];
                if (window.merge(l, -1, Integer::sum) == 0) {
                    window.remove(l);
                    formed--;
                }
                left++;
            }
        }
        return new int[]{bestL + 1, bestR + 1};   // 1-indexed
    }
}
```

**Kotlin 풀이**:

```kotlin
class Solution {
    fun solution(gems: Array<String>): IntArray {
        val required = gems.toSet().size
        val window = HashMap<String, Int>()
        var formed = 0
        var left = 0
        var bestLen = Int.MAX_VALUE
        var bestL = 0
        var bestR = 0
        for (right in gems.indices) {
            val g = gems[right]
            val nv = window.getOrDefault(g, 0) + 1
            window[g] = nv
            if (nv == 1) formed++
            while (formed == required) {
                if (right - left + 1 < bestLen) {
                    bestLen = right - left + 1
                    bestL = left
                    bestR = right
                }
                val l = gems[left]
                val newCnt = window[l]!! - 1
                if (newCnt == 0) {
                    window.remove(l)
                    formed--
                } else {
                    window[l] = newCnt
                }
                left++
            }
        }
        return intArrayOf(bestL + 1, bestR + 1)
    }
}
```

**복잡도**: 시간 O(n), 공간 O(distinct).

**함정**:
- 1-indexed 반환 — `+1` 빠뜨리면 오답.
- 동일 길이 시 start 작은 것 — `<` (strict) 비교라 자동으로 가장 왼쪽 우선.
- formed 갱신은 `window.get == 1`일 때만 ++, `== 0`일 때만 --. cover 종류 수의 정확한 추적.

---

## 7. 함정·엣지케이스

### 7.1 입력 경계

| 케이스 | 코드 동작 | 대응 |
|---|---|---|
| `s = ""` (빈 문자열) | for 루프 0회, best=0 반환 | 보통 OK, 명시적 체크 불필요 |
| `k = 0` (윈도우 크기 0) | 고정 윈도우면 `n - k + 1 = n + 1` 오프바이원 | k≥1 입력 가정 확인, 아니면 early return |
| `n < k` | 결과 배열 음수 길이 → NegativeArraySizeException | early return `new int[0]` |
| 단일 원소 `[x]` | left=right=0, while 안 들어감, best=1 | OK |
| 전부 같은 원소 `[5,5,5]` | shrink 패턴마다 다름 — 직접 검증 | 테스트 필수 |

### 7.2 음수 포함 배열 + sum 조건

```
[2, -1, 3, -2, 4],  target = 4 인 sum ≥ target 최단

window expand → sum 증가  (양수만일 때)
음수가 섞이면 expand해도 sum 감소 가능 → "sum이 target 넘었으니 shrink" 논리 깨짐.
```

**해결책**: 음수 포함이면 **prefix sum + monotonic deque** 또는 **prefix sum + TreeMap**. sliding window는 monotonic 조건이 필요 (sum 단조 증가 = 양수 only).

**LeetCode 862** "Shortest Subarray with Sum at Least K" 는 음수 허용 — sliding window 안 됨, deque 필요.

### 7.3 char count vs HashMap count

| | `int[26]` / `int[128]` | `HashMap<Character, Integer>` |
|---|---|---|
| 속도 | 매우 빠름 (배열 인덱싱) | 2~5배 느림 (boxing + hash) |
| 메모리 | 작음 (104 / 512 bytes) | Node 객체 alloc |
| 적용 | ASCII, 알파벳만 | 유니코드, 임의 객체 |
| 라이브 코딩 | **무조건 우선** | string이 아닌 경우만 |

LeetCode 76/438/567/424 모두 ASCII — `int[128]` 또는 `int[26]`이 정답. 시간 빠듯한 라이브에서 HashMap 쓰면 P99에서 TLE 위험.

### 7.4 K=0 / K=1 같은 trivial 케이스

- LeetCode 424 (`k=0`): "어떤 교체도 못함" → 가장 긴 동일 문자 연속. 위 코드는 그대로 동작 (maxFreq=windowLen이면 shrink 안 함).
- LeetCode 424 (`k ≥ n`): 모든 문자 교체 가능 → 답 = n.
- 의도적 테스트하라.

### 7.5 Integer 비교 함정

```java
Map<Character, Integer> map = ...;
if (map.get('a') == 2) { ... }   // Integer == int 자동 unbox: OK
if (map.get('a') == map2.get('a')) { ... }   // Integer == Integer: 캐시 밖에선 false!
```

`Integer` 객체 비교는 `-128 ~ 127` 캐시 범위 밖에서 `==`가 false. 반드시 `.intValue()` 또는 `.equals()`. `int[]` 쓰면 이 문제 자체가 없음 — 또 한 번 배열이 우월한 이유.

### 7.6 invariant 한 방향

sliding window는 **단조 조건**에서만 작동:
- "sum > target → shrink" : 양수 배열에서만 sum이 단조 증가.
- "distinct > K → shrink" : distinct는 expand 시 ≤ +1, shrink 시 ≥ -1 (단조 일관).

invariant가 expand/shrink 방향에 따라 단조롭게 변하지 않으면 sliding window 적용 불가 — DP나 다른 패턴으로.

---

## 8. 꼬리질문 트리

라이브 코딩에서 면접관이 던지는 후속 질문에 대비.

### Q1. "이 문제 윈도우가 고정인지 가변인지 어떻게 판단?"

> 문제에 **K가 명시**되어 있으면 고정 ("길이 K인 부분 배열의 ..."). **조건을 만족하는 가장 긴/짧은**이면 가변. 둘 다 아니면 sliding window가 아닐 수 있다 — Two Pointers/DP/Prefix Sum 의심.

### Q2. "더 빠르게 할 수 있나?"

> sliding window는 이미 O(n). 더 빨리는 못 가는 게 일반적. 다만 (1) 자료구조 교체 (HashMap → int[26])로 상수 줄이기, (2) 미리 sum/prefix 계산해서 윈도우 자체 없애기 (특정 변형). 무조건 더 빠른 알고리즘 있다고 가정하지 말 것.

### Q3. "메모리를 더 줄이려면?"

> count map 대신 int[Σ] 배열 (Σ가 작을 때). bit 연산 가능한 문제(예: 부분 문자열에 등장하는 글자 종류만 추적)면 `int` 한 개로 bitmask. 그 외엔 sliding window 자체가 이미 O(1) 또는 O(K) 보조 공간이라 더 줄일 여지 적음.

### Q4. "스트리밍/온라인이라면?"

> 입력이 한 번에 안 들어오고 한 원소씩 도착하면 sliding window의 **right 증가 + 가끔 left 증가** 패턴이 그대로 적용. 단:
> - **고정 길이 K**: 큐에 푸시하면서 K 초과 시 폴. monotonic deque 그대로.
> - **가변 길이**: invariant 위반 시 left 증가 — 동일.
> - **무한 스트림**: 결과를 항상 들고 있어야 (예: "지금까지 본 sliding window max"). 추가 자료구조로 답 유지.

이게 production에서 sliding window가 쓰이는 본질. **rate limiter, observability, network congestion** 모두 스트리밍.

### Q5. "정확히 K개를 만족하는 부분 배열 개수는?"

> **트릭**: `atMost(K) - atMost(K-1)`. 정확히 K = (최대 K개) − (최대 K−1개). 각각 sliding window로 O(n) → 전체 O(n).
>
> 예: LeetCode 992 "Subarrays with K Different Integers".
>
> 직접 "= K"를 sliding window로 풀면 invariant가 양방향 모두 위반 가능 (확장하면 K 초과, 수축하면 K 미만) → 단조 깨짐 → sliding window 불가. 따라서 ≤K로 우회.

### Q6. "음수가 들어오면?"

> sum 기반 sliding window는 sum monotonic 깨져서 불가. **prefix sum + monotonic deque** (LeetCode 862) 또는 **prefix sum + TreeMap** (logN으로 더 일반적).

### Q7. "min/max 추적 자료구조를 deque 외에 뭐 있나?"

> (1) `TreeMap<Integer, Integer>` (값 → 개수) — O(log K) per op, lazy delete 가능. (2) two heap (max-heap + lazy delete)로 deletion 우회 — 구현 까다로움. (3) `MultiSet` 라이브러리 (C++ STL). 라이브 코딩에선 deque가 최선.

### Q8. "left와 right가 둘 다 N번 움직인다 증명?"

> 둘 다 단조 증가, 최대값 N-1. 따라서 각자 최대 N번 증가. 전체 step 2N → amortized O(1)/op → O(n). 내부 while 보이지만 left가 한 번 가면 다신 안 돌아온다는 게 핵심.

### Q9. "Java 18 이상 / 모던 API 쓸 수 있나?"

> `s.codePoints()`로 unicode-safe iteration, `String.indexOf(int codepoint, int from)`로 surrogate 안전 검색. 단 라이브 코딩에선 ASCII 문제 99% — 굳이 codepoint 안 써도 됨. 면접관이 "이모지 포함" 케이스 던지면 codepoint로 전환.

---

## 9. 다른 패턴과의 연결

### 9.1 Two Pointer의 확장형

```
Two Pointer    →    Sliding Window
양 끝 수렴           같은 출발 + 둘 다 오른쪽
"쌍" 답              "구간" 답
정렬 필요             정렬 불필요 (대개)
```

Sliding window = "Two Pointer가 둘 다 같은 방향으로 가는 특수 경우". 둘 다 amortized O(n) 원리 동일.

### 9.2 Prefix Sum과의 결합

```
sum(A[i..j]) = prefix[j+1] - prefix[i]
```

- sliding window: 연속 구간 + 단조 조건 (양수 sum). O(n).
- prefix sum + HashMap: 연속 구간 + 임의 sum (음수 OK). O(n).
- prefix sum + monotonic deque: 음수 + min length with sum ≥ K. O(n).
- prefix sum + binary search: 정렬된 prefix (양수일 때만). O(n log n).

**판정**: 양수만이면 sliding window가 가장 빠르고 메모리 적음. 음수 섞이면 prefix sum 계열.

### 9.3 Monotonic Deque로 확장

```
sliding window + max/min  →  monotonic deque
sliding window + sorted   →  TreeMap / multiset
sliding window + count    →  count map (HashMap or int[Σ])
sliding window + sum      →  long sum (증분 갱신)
```

각 추가 요구사항이 보조 자료구조를 결정. 본질은 sliding window 골격 그대로.

### 9.4 Heap과의 관계

"sliding window의 K번째 큰 값"은 heap으로 풀리지만 deletion이 까다로워 lazy deletion (TreeMap이 더 쉬움). LeetCode 480 "Sliding Window Median" 이 그 예.

### 9.5 DP와의 관계

일부 DP 문제는 "최근 K개의 상태만 보면 됨"으로 환원 가능 → **sliding window DP** (monotonic deque optimization). 예: LeetCode 1696 "Jump Game VI" — DP를 sliding window max로 가속해 O(NK) → O(N).

---

## 10. 시니어 운영 연결 — sliding window가 production에서 사는 곳

> 라이브 코딩의 sliding window를 인프라/observability/네트워크의 실제 시스템과 매핑할 수 있어야 시니어.

### 10.1 Rate Limiter Sliding Window 알고리즘

```
요청 시각 (epoch ms):
   ─────────────────── 60초 윈도우 ────────────────────────────▶
        request1   request2   request3                request4
        t=12:00:01 t=12:00:15 t=12:00:30              t=12:01:05
                            ▲                              ▲
                            현재 시각 t=12:00:31           새 요청 도착
                            (window: 12:00:01~12:00:30)

알고리즘:
  for each request at time t:
      while (queue.first().time <= t - 60s):  queue.removeFirst()  ← shrink
      if (queue.size() >= LIMIT):  reject
      queue.addLast(t)                                              ← expand
```

이게 사실상 **고정 시간 윈도우 + 가변 카운트**. Nginx `limit_req`, AWS API Gateway throttling, Redis `INCR` + TTL 모두 이 패턴의 변형.

**최적화 — Fixed Window vs Sliding Window**:
- **Fixed Window**: 1분 단위 bucket. 단순. boundary에서 2배 burst 가능 (12:00:59에 100, 12:01:00에 100).
- **Sliding Window Counter**: 두 bucket weighted average — Cloudflare blog 유명. 메모리 적고 burst 방어 OK.
- **Sliding Window Log**: 모든 요청 timestamp 저장. 정확하지만 메모리 O(요청 수).

라이브 코딩의 LeetCode 209/3과 운영의 rate limiter는 **같은 sliding window** — 다만 인덱스가 시간축이라는 차이.

### 10.2 Log Streaming 최근 N초 통계

```
Kafka topic "access_log" → consumer
   each event: { time, latency_ms }

목표: "최근 5분 P99 latency"

→ time-windowed deque, 5분 expire
   on event:
     dq.addLast((time, latency))
     while (dq.first().time < now - 5분): dq.removeFirst()
     // 윈도우 안에서 P99 계산: TreeMap or t-digest
```

Apache Flink/Kafka Streams의 **tumbling/hopping/sliding window**가 이 패턴의 산업화. Prometheus `rate(metric[5m])` 도 sliding window의 PromQL 표현.

### 10.3 네트워크 TCP Congestion Window

TCP `cwnd` (congestion window) — 송신 측이 ACK 받기 전 보낼 수 있는 최대 segment 수. Slow start → Congestion avoidance → AIMD (additive increase, multiplicative decrease). 윈도우가 **가변 크기**로 expand/shrink하며 네트워크 상황에 적응 — sliding window의 통신 분야 원형.

같은 단어 "sliding window"가 알고리즘 / TCP / rate limiter에서 등장하는 건 우연이 아니라 동일 패러다임.

### 10.4 Observability — 이상치 탐지

```
metric stream: cpu[t], cpu[t+1], cpu[t+2], ...
        sliding window 1분 평균 / 표준편차 / quantile
            → anomaly: |x - μ| > 3σ
```

Datadog / New Relic / Grafana의 anomaly detector 다수가 sliding window 평균·분산 기반 (EWMA = 지수 가중 sliding window). 단순 평균 대신 모든 변형이 sliding window 원리.

### 10.5 Database — Window Function

SQL `OVER (ORDER BY ts ROWS BETWEEN 5 PRECEDING AND CURRENT ROW)` — 이게 진짜 SQL의 sliding window. PostgreSQL/Oracle/Redshift 모두 sliding window function 지원. PromQL의 `[5m]`, InfluxDB의 `GROUP BY time(5m, 1m)` 모두 같은 패러다임.

### 10.6 운영 시그널 매핑

| 증상 | sliding window 관점 | 해결 |
|---|---|---|
| API rate limit "정확히 분 경계마다 2배 burst" | fixed window → sliding window counter로 교체 | Cloudflare 방식 |
| "최근 5분 P99 latency" 매번 풀스캔으로 느림 | streaming sliding window + t-digest로 incremental | Flink, KSqlDB |
| TCP 처리량 낮음 + retransmit 많음 | cwnd가 작게 유지됨 | BBR (sliding window 기반 bandwidth probe) |
| anomaly detection false positive 많음 | 윈도우 너무 짧음 — variance 큼 | 윈도우 늘리고 EWMA로 smooth |

> 시니어는 **"이 문제 sliding window네"** 를 라이브 코딩에서도, prod incident에서도, 시스템 디자인에서도 같은 깊이로 본다. 이게 진짜 마스터.

---

## 11. 마지막 한 줄 — sliding window라는 단어를 들으면

> bucket이 아니라 **자(ruler)**. left/right 두 인덱스가 단조 증가만 한다는 **amortized O(n)** 증명. invariant 한 줄 정의. 4형태 (고정/가변/카운트/deque) boilerplate. 음수 함정. atMost(K) − atMost(K−1) 트릭. ASCII면 int[26] 우선. 그리고 production에선 rate limiter, log streaming, TCP cwnd, window function 모두 같은 패턴.
>
> 라이브 코딩에서 "연속(contiguous)" + "최대/최소/개수"가 보이면 30초 안에 sliding window로 분류, 5분 안에 invariant 적고 boilerplate 적용, 10분 안에 엣지케이스(빈 입력, K=0, 음수)까지 짚는다. 이게 sliding window를 **마스터**한 사람이다.
