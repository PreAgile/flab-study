# 07. Binary Search (이분 탐색)

> "정렬된 배열에서 값 찾기"는 입문자.
> 마스터는 **단조성(monotonicity)** 이 보이는 모든 문제에 이분 탐색을 꽂는다. "정렬된 배열"은 그 중 가장 단순한 형태일 뿐이고, 실전에서는 "답 자체를 이분 탐색" (parametric search) 이 더 많이 나온다. 회전 배열의 두 절반 중 어느 쪽이 정렬돼 있는지 가르고, lower_bound / upper_bound 의 미세한 부등호 차이로 중복 처리 의도까지 표현하는 — 그게 마스터 수준이다.
>
> 이 챕터는 옵션값 외우기 대신 본질(단조성)·왜(왜 그 부등호인지)·연결(DB index, sorted log, parametric → DP/그리디 결합)·운영 진단까지 다룬다.

---

## 0. 인지 신호 — 이 패턴을 의심해야 하는 순간

문제 설명에서 다음 중 하나라도 보이면 즉시 이분 탐색을 1순위 후보로 올린다.

| 신호 | 예시 키워드 | 변형 |
|---|---|---|
| **정렬된 입력** | "오름차순 정렬된 배열", "non-decreasing", "sorted" | 표준 binary search |
| **삽입 위치 / 첫 번째 / 마지막** | "처음으로 X 이상이 나오는 index", "X 이하의 마지막 index" | lower_bound / upper_bound |
| **회전된 정렬 배열** | "어떤 pivot에서 회전된", "rotated sorted array" | 회전 배열 search |
| **peak / valley** | "양쪽 이웃보다 큰 원소", "단봉 (unimodal)" | peak finding |
| **답을 이분 탐색** | "최소 시간으로 가능한가?", "최대 무게는 얼마까지 가능한가?", "K일 안에 끝낼 수 있는 가장 느린 속도" | **parametric search** |
| **단조 함수의 근** | `f(x)` 가 단조 증가/감소, `f(x) >= T` 의 최소 x | parametric search |
| **결정 문제(decision)로 환원 가능** | "가능한가? yes/no" 가 답 후보의 단조 함수 | parametric search |
| **로그(logN) 시간을 요구** | "10^9 입력, 1초 안에" | binary search 또는 hash |

특히 마지막 4개 — "답을 이분 탐색" — 가 한국 라이브 코딩 테스트 (프로그래머스 lv 3 단골) 의 정공법이다. 표면적으로는 그리디·DP처럼 보이는데 풀이가 안 떠오를 때, **"답 후보 범위에 단조성이 있는가?"** 를 묻는 순간 풀린다.

### Anti-signal — 이분 탐색이 **아닌** 경우

- 단조성 없음 — 답 X 가 가능하면 X+1 은 불가능, 같은 식으로 뒤집힘 → 이분 X
- 입력이 정렬되어 있지 않고 한 번만 쓸 거면 정렬 비용 O(N log N) > 선형 탐색 O(N)
- 매우 작은 N (≤ 100) — 상수 차이는 신경 쓸 가치 없음

---

## 1. 백지 그리기

### 1.1 표준 binary search

```
정렬된 배열 [1, 3, 5, 7, 9, 11, 13, 15, 17, 19], target = 11

lo                                          hi
 ▼                                           ▼
[ 1,  3,  5,  7,  9, 11, 13, 15, 17, 19]
                    ▲
                   mid = (0+9)/2 = 4
                   arr[4]=9 < 11  →  lo = mid+1

              lo                             hi
               ▼                              ▼
[              11, 13, 15, 17, 19]
                       ▲
                      mid = (5+9)/2 = 7
                      arr[7]=15 > 11  →  hi = mid-1

              lo            hi
               ▼             ▼
[              11, 13, 15]
                   ▲
                  mid = (5+6)/2 = 5
                  arr[5]=11 == target  →  return 5
```

핵심: **매 step 탐색 공간 반으로**. N → N/2 → N/4 → ... → 1, 총 log₂N step.

### 1.2 lower_bound vs upper_bound — 부등호 한 글자 차이

```
배열 [1, 2, 2, 2, 3, 4],  target = 2

lower_bound(2): 첫 번째로 "2 이상" 인 index  →  1
upper_bound(2): 첫 번째로 "2 초과" 인 index  →  4
                    ↑
              (= 2의 마지막 다음 index = 4)

  index    0   1   2   3   4   5
  value  [ 1,  2,  2,  2,  3,  4]
               ▲           ▲
            lower_b       upper_b

  count of 2 = upper_b - lower_b = 4 - 1 = 3
```

→ "정확한 값 위치" 가 아니라 **경계** 를 찾는 게 본질. 중복이 있는 정렬 배열에서 `equals` 위치는 의미가 모호하지만, **lower/upper bound 는 항상 유일하게 정의** 된다. C++ STL `lower_bound/upper_bound`, Java `Collections.binarySearch` 의 음수 반환값 (`-(insertion point) - 1`), Python `bisect_left/bisect_right` 가 전부 이 개념.

### 1.3 회전 배열 — 어느 절반이 정렬돼 있는가

```
원본 [0, 1, 2, 4, 5, 6, 7]  →  pivot=3에서 회전  →  [4, 5, 6, 7, 0, 1, 2]

                                  mid
                                   ▼
[ 4,  5,  6,  7,  0,  1,  2]
  ▲                       ▲
  lo                      hi

arr[lo]=4 ≤ arr[mid]=7  →  왼쪽 [lo..mid] 가 정렬됨
                          ┌─────────────┐
                          │  4  5  6  7 │   ← 이 구간만 표준 binary search 가능
                          └─────────────┘
target=1 이 [4..7] 범위에 있나? 아니오 → lo = mid+1 (오른쪽으로)

      lo (after)
       ▼
[              0,  1,  2]
               ▲       ▲
              lo       hi
              mid = (4+6)/2 = 5
arr[5]=1 == target  →  return 5
```

**핵심 통찰**: 회전 배열에서는 `mid` 양쪽 중 **정확히 한 쪽은 반드시 정렬돼 있다** (회전 1회 가정). 정렬된 쪽에서 target 이 그 범위 안에 있는지 판단 → 있으면 그쪽으로, 없으면 반대로. 이 한 가지 결정만 추가되면 표준 binary search 가 그대로 작동.

```
[정렬 판정 표]
        if arr[lo] <= arr[mid]:                    # 왼쪽 정렬
            if arr[lo] <= target < arr[mid]:       # target 이 그 안에
                hi = mid - 1                       # 왼쪽으로
            else:
                lo = mid + 1                       # 오른쪽으로
        else:                                      # 오른쪽 정렬
            if arr[mid] < target <= arr[hi]:       # target 이 그 안에
                lo = mid + 1                       # 오른쪽으로
            else:
                hi = mid - 1                       # 왼쪽으로
```

### 1.4 Parametric Search — "답을 이분 탐색"

```
[코코 바나나 LC 875]
N = 4 더미, piles = [3,6,7,11], H = 8시간
질문: K (시간당 먹는 속도) 의 최솟값은?

답 후보 K의 범위: 1 ~ max(piles) = 11
각 K 에 대해 결정 함수 feasible(K) = "이 속도로 H 시간 안에 다 먹을 수 있나?"

  K   :  1    2    3    4    5    6    7    8    9   10   11
 feas :  N    N    N    N    Y    Y    Y    Y    Y    Y    Y
                              ▲
                              ┕━━ 첫 번째 Y = 답

  단조성:  K 가 크면 더 빨리 먹음  →  K↑ 일수록 feasible 더 잘 됨
          한 번 Y 가 되면 그 이후는 영원히 Y  →  이분 탐색 가능
```

이 그림이 parametric search 의 모든 것이다. **답 후보를 이분 탐색**, 각 후보에서 결정 함수 (yes/no) 호출, **결정 함수가 단조** 라는 게 적용 조건. 결정 함수의 시간 복잡도 D 라면 전체 `O(log(answer_range) * D)`.

### 1.5 백지에서 그릴 수 있어야 하는 4개의 그림

1. **표준** — `lo, hi, mid` 가 좁혀가는 그림 (1.1)
2. **lower / upper bound 차이** — 중복 원소에서 양쪽 경계 (1.2)
3. **회전 배열의 두 절반 중 정렬된 쪽** — 결정 분기 (1.3)
4. **parametric** — 답 후보 축 위에 N/N/N/Y/Y/Y 라벨, 첫 Y 가 답 (1.4)

이 4개를 그릴 수 있으면 이 챕터를 80% 마스터.

---

## 2. 직관과 정의

### 2.1 본질은 단조성 (monotonicity)

이분 탐색의 본질은 "정렬된 배열" 이 아니다 — **단조성** 이다.

- 배열이 정렬돼 있다 = "index 가 커질수록 값이 단조 증가" 라는 단조성
- parametric search = "답 후보 X 가 커질수록 결정 함수 결과가 단조 (한 번 Y 면 그 후 영원히 Y, 또는 그 반대)"
- 회전 배열에서도 절반은 단조, 그 절반에서만 이분 탐색

→ **"정렬"은 단조성의 한 형태일 뿐**. 단조성이 있는 어떤 함수에도 이분 탐색이 통한다. 시니어는 문제에서 단조성을 추출하는 훈련을 한다.

### 2.2 정확한 정의

> 단조 함수 `f: [lo, hi] → {0, 1}` 에서 `f(x) = 1` 인 최소 x (또는 최대 x) 를 `O(log(hi - lo))` 시간에 찾는다.

- `f` 가 array indexing 이면 → 표준 binary search
- `f` 가 결정 함수 (decision predicate) 이면 → parametric search
- `f` 가 두 부분 단조 (회전) 면 → 추가 case 분기 후 적용

### 2.3 `(lo + hi) / 2` overflow

```java
int mid = (lo + hi) / 2;            // ❌ lo + hi 가 Integer.MAX_VALUE 넘으면 overflow → 음수
int mid = lo + (hi - lo) / 2;       // ✅ overflow 안전
int mid = (lo + hi) >>> 1;          // ✅ unsigned shift, Java JDK 표준 Arrays.binarySearch 방식
```

**왜 중요?**

- LeetCode 32-bit 환경에서 `lo + hi` 가 `Integer.MAX_VALUE` (≈ 2.1 × 10⁹) 을 넘는 경우는 사실 드물지만, **parametric search 에서 답 후보가 10⁹ 근처면 충분히 가능**.
- 면접관이 즉시 잡는 함정. JDK 의 `Arrays.binarySearch` 도 1.2 → 1.6 패치에서 `>>>` 로 바뀐 역사가 있음 (Joshua Bloch, 2006 "Extra, Extra - Read All About It: Nearly All Binary Searches and Mergesorts are Broken").
- Production B-tree, search engine, scientific computing 어디서나 동일 버그. **시니어가 코드 리뷰에서 가장 자주 잡는 보안/안정성 결함 중 하나**.

### 2.4 while `lo < hi` vs `lo <= hi` — 두 가지 경계 패턴

여기서 99% 의 buggy binary search 가 발생한다. 두 가지 패턴을 분명히 구분.

```
[패턴 A: 표준 search, "값 정확히 찾기"]
while (lo <= hi) {
    int mid = lo + (hi - lo) / 2;
    if (arr[mid] == target) return mid;
    else if (arr[mid] < target) lo = mid + 1;
    else hi = mid - 1;
}
return -1;
// 종료: lo > hi, 못 찾음

[패턴 B: lower_bound / upper_bound, "경계 찾기"]
while (lo < hi) {
    int mid = lo + (hi - lo) / 2;
    if (arr[mid] < target) lo = mid + 1;   // lower_bound 의 핵심 부등호
    else                   hi = mid;        // hi = mid (mid-1 아님!)
}
return lo;
// 종료: lo == hi, 그 값이 답
```

**왜 두 패턴이 다른가?**

- 패턴 A: 답이 `[lo, hi]` 의 **닫힌 구간** 에 있다고 보고, 못 찾으면 종료. `mid` 가 답 아니면 후보에서 제외 → `lo = mid+1` 또는 `hi = mid-1`.
- 패턴 B: 답이 `[lo, hi)` 의 **반열린 구간** 에 있다고 보고, 구간이 1 원소로 줄면 그게 답. `mid` 가 답일 가능성이 있으면 후보에 남김 → `hi = mid` (mid 를 후보 유지).

**선택 기준**: 정확히 같은 값을 찾을 때는 패턴 A, "경계" (lower_bound, upper_bound, parametric search 의 첫 Y) 를 찾을 때는 패턴 B. 라이브 코딩 테스트에서는 **두 가지 변형 다 외우는 게 아니라**, **패턴 B 하나로 통일** 하는 게 안전하다 (값을 찾고 싶으면 lower_bound 결과를 한 번 더 검증).

### 2.5 무한 루프 방지

```java
// ❌ 무한 루프 예시
while (lo < hi) {
    int mid = (lo + hi) / 2;        // lo=1, hi=2 → mid=1
    if (cond(mid)) lo = mid;        // lo=1 그대로 → 무한
    else           hi = mid - 1;
}
```

`lo = mid` (mid 포함 후보 유지) 를 쓰면 mid 계산 시 **상위 쪽으로 반올림** 해야 함: `mid = lo + (hi - lo + 1) / 2`. 이는 "마지막 Y" (upper bound 변형, 가장 큰 가능 답) 를 찾을 때 자주 등장.

```java
// 마지막 Y (가장 큰 가능 K) 찾기 - "최대 가능 답" 패턴
while (lo < hi) {
    int mid = lo + (hi - lo + 1) / 2;   // 상위 반올림
    if (feasible(mid)) lo = mid;        // mid 가능 → 더 큰 거 시도, lo = mid
    else               hi = mid - 1;
}
return lo;
```

**암기 트릭**:
- `hi = mid` 쓰면 → `mid = lo + (hi-lo)/2` (하위 반올림)
- `lo = mid` 쓰면 → `mid = lo + (hi-lo+1)/2` (상위 반올림)
- 둘 다 mid-1 / mid+1 을 한쪽에 쓰는 게 정상, 양쪽 모두 mid 면 무한 루프 의심.

---

## 3. Java 템플릿

### 3.1 표준 binary search (값 찾기)

```java
// 패턴 A: 값 정확히 찾기, 못 찾으면 -1
public int binarySearch(int[] arr, int target) {
    int lo = 0, hi = arr.length - 1;
    while (lo <= hi) {
        int mid = lo + (hi - lo) / 2;     // overflow 안전
        if (arr[mid] == target) return mid;
        else if (arr[mid] < target) lo = mid + 1;
        else                        hi = mid - 1;
    }
    return -1;
}
```

### 3.2 lower_bound — 첫 번째로 `>= target` 인 index

```java
// 패턴 B: target 이 들어갈 가장 왼쪽 위치 (= 첫 번째 >= target)
// arr 에 target 이 없으면 "들어가야 할 위치" 를 반환 (= LeetCode 35 Search Insert Position)
public int lowerBound(int[] arr, int target) {
    int lo = 0, hi = arr.length;          // hi = length (반열린 구간 [lo, hi))
    while (lo < hi) {
        int mid = lo + (hi - lo) / 2;
        if (arr[mid] < target) lo = mid + 1;
        else                   hi = mid;   // mid 도 후보 → hi = mid
    }
    return lo;                             // lo == hi 가 답
}
```

### 3.3 upper_bound — 첫 번째로 `> target` 인 index

```java
public int upperBound(int[] arr, int target) {
    int lo = 0, hi = arr.length;
    while (lo < hi) {
        int mid = lo + (hi - lo) / 2;
        if (arr[mid] <= target) lo = mid + 1;   // <= 로 한 글자 차이
        else                    hi = mid;
    }
    return lo;
}

// count of target = upperBound(target) - lowerBound(target)
```

### 3.4 회전 배열 search (LC 33)

```java
public int searchRotated(int[] arr, int target) {
    int lo = 0, hi = arr.length - 1;
    while (lo <= hi) {
        int mid = lo + (hi - lo) / 2;
        if (arr[mid] == target) return mid;

        if (arr[lo] <= arr[mid]) {                       // 왼쪽 절반이 정렬됨
            if (arr[lo] <= target && target < arr[mid]) {
                hi = mid - 1;
            } else {
                lo = mid + 1;
            }
        } else {                                         // 오른쪽 절반이 정렬됨
            if (arr[mid] < target && target <= arr[hi]) {
                lo = mid + 1;
            } else {
                hi = mid - 1;
            }
        }
    }
    return -1;
}
```

**핵심 트릭**: `arr[lo] <= arr[mid]` 부등호에 `=` 가 있는 이유는 `lo == mid` (구간 길이 1~2) 일 때를 정상 처리하기 위해서. 빼면 edge case 에서 무한 루프.

### 3.5 Parametric search — 결정 함수 분리

```java
// LC 875 Koko Eating Bananas — 시간당 K개 먹어서 H 시간 안에 끝낼 최소 K
public int minEatingSpeed(int[] piles, int h) {
    int lo = 1, hi = 0;
    for (int p : piles) hi = Math.max(hi, p);   // 답 후보 최대값 = max(piles)

    while (lo < hi) {
        int mid = lo + (hi - lo) / 2;
        if (canFinish(piles, mid, h)) hi = mid;   // 가능 → 더 작게
        else                          lo = mid + 1;
    }
    return lo;
}

private boolean canFinish(int[] piles, int k, int h) {
    long hours = 0;
    for (int p : piles) {
        hours += (p + k - 1) / k;     // ceil(p / k) — overflow 없는 정수 나눗셈
        if (hours > h) return false;  // 조기 종료 (large piles 에서 중요)
    }
    return hours <= h;
}
```

**결정 함수 작성 4 step**:
1. **함수 시그니처** — `boolean feasible(int x)`. 답 후보 x 를 받고 yes/no.
2. **단조성 검증** — `x` 가 커질수록 (또는 작아질수록) 결과가 한 방향으로만 바뀌는가? 증명/직관 확보.
3. **답 후보 범위** — `lo`, `hi` 의 명확한 경계. 너무 좁으면 답 누락, 너무 넓으면 overflow.
4. **루프 패턴** — "첫 번째 Y" 찾기면 패턴 B + `hi = mid`, "마지막 Y" 찾기면 패턴 B + `lo = mid` (mid 상위 반올림).

### 3.6 Find Minimum in Rotated Sorted Array (LC 153)

```java
public int findMin(int[] arr) {
    int lo = 0, hi = arr.length - 1;
    while (lo < hi) {
        int mid = lo + (hi - lo) / 2;
        if (arr[mid] > arr[hi]) lo = mid + 1;   // min 은 mid 오른쪽
        else                    hi = mid;        // min 은 mid 포함 왼쪽
    }
    return arr[lo];
}
```

**왜 `arr[hi]` 와 비교?** `arr[lo]` 와 비교하면 회전이 안 된 경우 (`[1,2,3,4,5]`) 와 회전된 경우 (`[3,4,5,1,2]`) 를 구분 못 함. `arr[hi]` 와 비교하면 항상 일관됨 — `arr[mid] > arr[hi]` 면 `mid` 이전 어딘가에서 회전했다는 뜻 → min 은 `mid` 오른쪽.

### 3.7 Find Peak Element (LC 162)

```java
// arr[i-1] < arr[i] > arr[i+1] 인 peak 의 index 반환
// 가장자리는 -∞ 로 간주
public int findPeakElement(int[] arr) {
    int lo = 0, hi = arr.length - 1;
    while (lo < hi) {
        int mid = lo + (hi - lo) / 2;
        if (arr[mid] > arr[mid + 1]) hi = mid;       // 내리막 → peak 는 mid 포함 왼쪽
        else                         lo = mid + 1;   // 오르막 → peak 는 mid 오른쪽
    }
    return lo;
}
```

**놀라운 점**: 정렬되지 않은 배열인데도 이분 탐색이 통한다. 이유 — "양 끝이 -∞" 라는 가정 덕분에 **어딘가에는 반드시 peak 가 존재** 하고, 매 step `mid` 와 `mid+1` 의 비교로 "peak 가 어느 쪽에 반드시 있는지" 단조 결정 가능. 이게 단조성의 추상화 — "정렬" 이 본질이 아님을 보여주는 정수 예제.

---

## 4. Kotlin 템플릿

### 4.1 표준

```kotlin
fun binarySearch(arr: IntArray, target: Int): Int {
    var lo = 0
    var hi = arr.size - 1
    while (lo <= hi) {
        val mid = lo + (hi - lo) / 2
        when {
            arr[mid] == target -> return mid
            arr[mid] < target  -> lo = mid + 1
            else               -> hi = mid - 1
        }
    }
    return -1
}
```

### 4.2 lower_bound / upper_bound

```kotlin
fun lowerBound(arr: IntArray, target: Int): Int {
    var lo = 0
    var hi = arr.size
    while (lo < hi) {
        val mid = lo + (hi - lo) / 2
        if (arr[mid] < target) lo = mid + 1 else hi = mid
    }
    return lo
}

fun upperBound(arr: IntArray, target: Int): Int {
    var lo = 0
    var hi = arr.size
    while (lo < hi) {
        val mid = lo + (hi - lo) / 2
        if (arr[mid] <= target) lo = mid + 1 else hi = mid
    }
    return lo
}
```

### 4.3 Kotlin 표준 라이브러리 `binarySearch()`

```kotlin
// IntArray.binarySearch — JDK Arrays.binarySearch 와 동일
val idx = arr.binarySearch(target)
// 찾으면: idx ≥ 0 (정확한 index, 중복 있으면 어느 것인지 미지정)
// 못 찾으면: idx < 0, 삽입 위치는 -(idx + 1)

val insertionPoint = if (idx < 0) -(idx + 1) else idx
// insertionPoint == lowerBound(target) 와 동일 (찾았을 때 첫 발견이 lower 라는 보장은 없음!)

// 함정: 중복 원소가 있을 때 어떤 index 가 반환될지 보장 없음 → 면접에서는 직접 lowerBound 구현 권장
```

`List<T>.binarySearch { comparator }` 로 comparator 기반 변형도 가능. 단, 라이브 코딩 테스트에서는 직접 짜는 게 의도를 명확히 드러내고 중복 처리도 통제 가능.

### 4.4 회전 배열 (Kotlin)

```kotlin
fun searchRotated(arr: IntArray, target: Int): Int {
    var lo = 0
    var hi = arr.size - 1
    while (lo <= hi) {
        val mid = lo + (hi - lo) / 2
        if (arr[mid] == target) return mid
        if (arr[lo] <= arr[mid]) {
            if (target in arr[lo]..<arr[mid]) hi = mid - 1 else lo = mid + 1
        } else {
            if (target in (arr[mid] + 1)..arr[hi]) lo = mid + 1 else hi = mid - 1
        }
    }
    return -1
}
```

Kotlin 의 `in arr[lo]..<arr[mid]` (반열린) / `in (arr[mid]+1)..arr[hi]` (닫힌) 범위 표현이 가독성에 큰 도움.

### 4.5 Parametric (Koko)

```kotlin
fun minEatingSpeed(piles: IntArray, h: Int): Int {
    var lo = 1
    var hi = piles.max()
    while (lo < hi) {
        val mid = lo + (hi - lo) / 2
        if (canFinish(piles, mid, h)) hi = mid else lo = mid + 1
    }
    return lo
}

private fun canFinish(piles: IntArray, k: Int, h: Int): Boolean {
    var hours = 0L
    for (p in piles) {
        hours += (p + k - 1) / k
        if (hours > h) return false
    }
    return hours <= h
}
```

---

## 5. 시간/공간 복잡도

| 변형 | 시간 | 공간 | 비고 |
|---|---|---|---|
| 표준 binary search | O(log N) | O(1) | 재귀로 짜면 stack O(log N) |
| lower/upper bound | O(log N) | O(1) | 표준과 동일 |
| 회전 배열 search | O(log N) | O(1) | 한 step당 비교 횟수만 약간 증가 |
| Peak finding | O(log N) | O(1) | 정렬 안 된 배열인데도 log — 단조성의 추상 |
| Parametric search | O(log R × D) | O(D) | R = 답 후보 범위, D = 결정 함수 cost |
| 2D matrix binary search (LC 240) | O(M + N) | O(1) | 엄밀히는 이분 탐색 아니지만 변형 |

**Parametric 의 R 이 헷갈리는 포인트**:
- Koko: R = max(piles) ≤ 10⁹, log R ≈ 30. D = O(N). 전체 30N.
- Split Array (LC 410): R = sum(arr) ≤ 10⁹, log R ≈ 30. D = O(N). 동일.

→ **log(10⁹) ≈ 30** 은 외워둘 가치. parametric search 가 N=10⁵, 답=10⁹ 같은 입력에서 안전한 이유.

**왜 log N 이 빠른가** (운영 감각):
- N = 10⁹ 인 정렬 배열에서 binary search 는 약 30 step. 선형은 10⁹ step (1000배 느리고 메모리 fetch 패턴도 나쁨).
- B-tree (DB index) 의 깊이도 같은 이유로 log N. PostgreSQL B-tree 의 fanout 보통 ~250 → 10억 row 도 깊이 4~5.
- 30 step 의 cache miss vs 10⁹ 의 sequential read — modern CPU에서 sequential 이 cache-friendly 라 항상 1000배는 아니지만, **데이터셋이 RAM 초과** 하면 binary search 의 우위가 결정적 (disk seek 30번 vs full scan).

---

## 6. 대표 문제

### 6.1 LeetCode 704 — Binary Search

**문제**: 정렬된 배열에서 target 의 index 반환, 없으면 -1.

**접근**: 패턴 A 그대로.

```java
public int search(int[] nums, int target) {
    int lo = 0, hi = nums.length - 1;
    while (lo <= hi) {
        int mid = lo + (hi - lo) / 2;
        if (nums[mid] == target) return mid;
        else if (nums[mid] < target) lo = mid + 1;
        else                          hi = mid - 1;
    }
    return -1;
}
```

```kotlin
fun search(nums: IntArray, target: Int): Int {
    var lo = 0; var hi = nums.size - 1
    while (lo <= hi) {
        val mid = lo + (hi - lo) / 2
        when {
            nums[mid] == target -> return mid
            nums[mid] < target  -> lo = mid + 1
            else                -> hi = mid - 1
        }
    }
    return -1
}
```

**복잡도**: O(log N) / O(1).

**함정**: `(lo + hi) / 2` overflow. 빈 배열 (`length = 0`) 시 `hi = -1` 로 시작해 while 안 들어감 — 자동 처리.

### 6.2 LeetCode 35 — Search Insert Position (lower_bound)

**문제**: target 이 있으면 그 index, 없으면 삽입 위치 반환.

**접근**: 정확히 lower_bound. 패턴 B.

```java
public int searchInsert(int[] nums, int target) {
    int lo = 0, hi = nums.length;
    while (lo < hi) {
        int mid = lo + (hi - lo) / 2;
        if (nums[mid] < target) lo = mid + 1;
        else                    hi = mid;
    }
    return lo;
}
```

```kotlin
fun searchInsert(nums: IntArray, target: Int): Int {
    var lo = 0; var hi = nums.size
    while (lo < hi) {
        val mid = lo + (hi - lo) / 2
        if (nums[mid] < target) lo = mid + 1 else hi = mid
    }
    return lo
}
```

**복잡도**: O(log N).

**함정**:
- `hi = nums.length` (length-1 아님) — 빈 배열에 삽입할 수도 있어서.
- target 이 모든 원소보다 크면 `lo = nums.length` 반환 — 의도된 동작.

### 6.3 LeetCode 33 — Search in Rotated Sorted Array

**문제**: 회전된 정렬 배열에서 target index, 없으면 -1. 중복 없음.

**접근**: 매 step `mid` 의 어느 쪽이 정렬됐는지 판단 후, target 이 그 정렬된 쪽에 있는지로 분기.

```java
public int search(int[] nums, int target) {
    int lo = 0, hi = nums.length - 1;
    while (lo <= hi) {
        int mid = lo + (hi - lo) / 2;
        if (nums[mid] == target) return mid;

        if (nums[lo] <= nums[mid]) {                          // 왼쪽 정렬
            if (nums[lo] <= target && target < nums[mid]) hi = mid - 1;
            else                                          lo = mid + 1;
        } else {                                              // 오른쪽 정렬
            if (nums[mid] < target && target <= nums[hi]) lo = mid + 1;
            else                                          hi = mid - 1;
        }
    }
    return -1;
}
```

```kotlin
fun search(nums: IntArray, target: Int): Int {
    var lo = 0; var hi = nums.size - 1
    while (lo <= hi) {
        val mid = lo + (hi - lo) / 2
        if (nums[mid] == target) return mid
        if (nums[lo] <= nums[mid]) {
            if (target in nums[lo]..<nums[mid]) hi = mid - 1 else lo = mid + 1
        } else {
            if (target in (nums[mid] + 1)..nums[hi]) lo = mid + 1 else hi = mid - 1
        }
    }
    return -1
}
```

**복잡도**: O(log N).

**함정**:
- `nums[lo] <= nums[mid]` 의 `=` 누락 — 길이 1~2 구간에서 무한 루프.
- **중복 허용 변형 (LC 81)**: `nums[lo] == nums[mid] == nums[hi]` 면 정렬된 쪽 판정 불가 → `lo++, hi--` 로 한 칸씩 좁히기 → worst case O(N).
- 예: `[3,1]`, target=1 → lo=0, hi=1, mid=0, `nums[0]=3 > target=1` 이면서 `nums[0] <= nums[0]=3` (왼쪽 정렬). `nums[0]=3 <= 1` 거짓 → lo = mid+1 = 1 → 정답.

### 6.4 LeetCode 153 — Find Minimum in Rotated Sorted Array

**문제**: 회전된 배열에서 최솟값 반환. 중복 없음.

**접근**: `arr[hi]` 와 `arr[mid]` 비교. 패턴 B.

```java
public int findMin(int[] nums) {
    int lo = 0, hi = nums.length - 1;
    while (lo < hi) {
        int mid = lo + (hi - lo) / 2;
        if (nums[mid] > nums[hi]) lo = mid + 1;
        else                      hi = mid;
    }
    return nums[lo];
}
```

```kotlin
fun findMin(nums: IntArray): Int {
    var lo = 0; var hi = nums.size - 1
    while (lo < hi) {
        val mid = lo + (hi - lo) / 2
        if (nums[mid] > nums[hi]) lo = mid + 1 else hi = mid
    }
    return nums[lo]
}
```

**복잡도**: O(log N).

**왜 `nums[hi]` 와 비교?** `nums[lo]` 와 비교 시 정렬된 배열 (`[1,2,3]`) 에서 항상 `nums[lo] <= nums[mid]` → 오른쪽으로만 → 답이 nums[0] 인데 못 잡음. `nums[hi]` 비교는 일관됨.

**함정**: 중복 있는 LC 154 는 `nums[mid] == nums[hi]` 처리로 `hi--` 추가 → worst O(N).

### 6.5 LeetCode 162 — Find Peak Element

**문제**: `arr[i-1] < arr[i] > arr[i+1]` peak 의 index 반환. 경계는 `-∞` 가정. 다중 peak 면 아무거나.

**접근**: 정렬되지 않은 배열에서도 통하는 이분 탐색의 미학.

```java
public int findPeakElement(int[] nums) {
    int lo = 0, hi = nums.length - 1;
    while (lo < hi) {
        int mid = lo + (hi - lo) / 2;
        if (nums[mid] > nums[mid + 1]) hi = mid;
        else                           lo = mid + 1;
    }
    return lo;
}
```

```kotlin
fun findPeakElement(nums: IntArray): Int {
    var lo = 0; var hi = nums.size - 1
    while (lo < hi) {
        val mid = lo + (hi - lo) / 2
        if (nums[mid] > nums[mid + 1]) hi = mid else lo = mid + 1
    }
    return lo
}
```

**복잡도**: O(log N).

**왜 통하는가**: 양 끝이 `-∞` 라 어딘가에 peak 가 반드시 존재. `nums[mid] > nums[mid+1]` 이면 `mid` 또는 그 왼쪽에 peak (오르막에서 mid 에 도달했고 내리막으로 꺾인 거니까). `nums[mid] < nums[mid+1]` 이면 mid+1 또는 더 오른쪽에 peak. 단조 결정.

**함정**: `mid + 1` index out of bound — `lo < hi` 일 때 `mid < hi` 보장되므로 안전.

### 6.6 LeetCode 875 — Koko Eating Bananas (Parametric)

**문제**: piles[i] 만큼 바나나 있는 N 더미, H 시간 안에 다 먹어야 함. 시간당 K개 먹는 속도의 최솟값?

**단조성**: K↑ ⇒ 빨리 끝남 ⇒ feasible 더 잘 됨. NNNNYYYY 패턴.

**답 후보 범위**: K = 1 (느림) ~ max(piles) (한 시간에 한 더미 끝).

```java
public int minEatingSpeed(int[] piles, int h) {
    int lo = 1, hi = 0;
    for (int p : piles) hi = Math.max(hi, p);

    while (lo < hi) {
        int mid = lo + (hi - lo) / 2;
        if (canFinish(piles, mid, h)) hi = mid;
        else                          lo = mid + 1;
    }
    return lo;
}

private boolean canFinish(int[] piles, int k, int h) {
    long hours = 0;
    for (int p : piles) {
        hours += (p + k - 1) / k;       // ceil division
        if (hours > h) return false;
    }
    return hours <= h;
}
```

```kotlin
fun minEatingSpeed(piles: IntArray, h: Int): Int {
    var lo = 1; var hi = piles.max()
    while (lo < hi) {
        val mid = lo + (hi - lo) / 2
        if (canFinish(piles, mid, h)) hi = mid else lo = mid + 1
    }
    return lo
}

private fun canFinish(piles: IntArray, k: Int, h: Int): Boolean {
    var hours = 0L
    for (p in piles) {
        hours += (p + k - 1L) / k
        if (hours > h) return false
    }
    return hours <= h
}
```

**복잡도**: O(N log M), M = max(piles) ≤ 10⁹, log M ≈ 30.

**함정**:
- `hours` 가 `long` 이어야 함. `piles[i] ≤ 10⁹, N ≤ 10⁴` → 최악 10¹³, int overflow.
- ceil division: `(p + k - 1) / k` — 양수 한정. `Math.ceil((double)p / k)` 는 floating point 오차 위험 → 정수로.
- `lo = 1` (K=0 은 무의미, 무한 시간) 시작.

### 6.7 LeetCode 410 — Split Array Largest Sum (Parametric)

**문제**: 배열을 K 개 연속 부분 배열로 분할, 각 부분 합 중 최댓값이 최소가 되도록. 그 최댓값?

**단조성**: "최대 합 X 를 허용" → X↑ 면 더 적은 partition 으로 가능 → 분할 개수 ≤ K 면 feasible.

**답 후보 범위**: max(arr) (최소, 한 원소가 한 partition) ~ sum(arr) (최대, 모두 한 partition).

```java
public int splitArray(int[] nums, int k) {
    long lo = 0, hi = 0;
    for (int n : nums) { lo = Math.max(lo, n); hi += n; }

    while (lo < hi) {
        long mid = lo + (hi - lo) / 2;
        if (canSplit(nums, k, mid)) hi = mid;
        else                        lo = mid + 1;
    }
    return (int) lo;
}

// "각 partition 합 ≤ limit 으로 k 개 이하 partition 가능한가"
private boolean canSplit(int[] nums, int k, long limit) {
    int parts = 1;
    long cur = 0;
    for (int n : nums) {
        if (cur + n > limit) {
            parts++;
            cur = n;
            if (parts > k) return false;
        } else {
            cur += n;
        }
    }
    return true;
}
```

```kotlin
fun splitArray(nums: IntArray, k: Int): Int {
    var lo = 0L; var hi = 0L
    for (n in nums) { lo = maxOf(lo, n.toLong()); hi += n }
    while (lo < hi) {
        val mid = lo + (hi - lo) / 2
        if (canSplit(nums, k, mid)) hi = mid else lo = mid + 1
    }
    return lo.toInt()
}

private fun canSplit(nums: IntArray, k: Int, limit: Long): Boolean {
    var parts = 1
    var cur = 0L
    for (n in nums) {
        if (cur + n > limit) {
            parts++
            cur = n.toLong()
            if (parts > k) return false
        } else {
            cur += n
        }
    }
    return true
}
```

**복잡도**: O(N log S), S = sum(arr).

**함정**:
- DP 풀이 O(N²K) 도 있지만 parametric 이 훨씬 빠름.
- `lo = max(arr)` — 한 partition 의 합이 적어도 최대 원소 이상이어야 가능. 이 lo 가 답의 진짜 하한.
- 결정 함수에서 `parts > k` 조기 종료 필수 — 안 하면 의미 없는 partition 만 계속 증가.

### 6.8 프로그래머스 — 입국심사 (Parametric)

**문제**: N명, 심사관 M명, 각 심사관 i 의 심사 시간 times[i] (분). 모두 심사받는 데 걸리는 최소 시간?

**단조성**: 시간 T↑ ⇒ T 안에 심사 가능한 인원↑. NNNYYY. **첫 Y**.

**답 후보**: 1 ~ max(times) × N (가장 느린 심사관 혼자 다 처리).

```java
public long immigration(int n, int[] times) {
    long lo = 1, hi = 0;
    for (int t : times) hi = Math.max(hi, t);
    hi *= n;

    while (lo < hi) {
        long mid = lo + (hi - lo) / 2;
        if (canProcess(times, n, mid)) hi = mid;
        else                            lo = mid + 1;
    }
    return lo;
}

private boolean canProcess(int[] times, int n, long t) {
    long count = 0;
    for (int x : times) {
        count += t / x;
        if (count >= n) return true;       // 조기 종료 — overflow 방지에도 효과
    }
    return false;
}
```

```kotlin
fun immigration(n: Int, times: IntArray): Long {
    var lo = 1L
    var hi = times.max().toLong() * n
    while (lo < hi) {
        val mid = lo + (hi - lo) / 2
        if (canProcess(times, n, mid)) hi = mid else lo = mid + 1
    }
    return lo
}

private fun canProcess(times: IntArray, n: Int, t: Long): Boolean {
    var count = 0L
    for (x in times) {
        count += t / x
        if (count >= n) return true
    }
    return false
}
```

**복잡도**: O(M log(max(times) × N)), M = 심사관 수.

**함정**:
- hi = max(times) × N → 10⁹ × 10⁹ = 10¹⁸, **long 필수**.
- 조기 종료 `count >= n` 없으면 N=10⁹ 케이스에서 count 가 long overflow 직전까지 가서 비효율.
- 직관적으로는 그리디 (느린 심사관 빼기) 가 보이지만 증명/구현 어려움 — parametric 이 정공법.

### 6.9 프로그래머스 — 징검다리 건너기 (Parametric)

**문제**: 돌 N개, 각 돌 stones[i] 명까지 건넘. K칸 연속 0 이면 못 건넘. 건널 수 있는 최대 인원?

**단조성**: 인원 X↑ ⇒ 못 건넘 (더 많은 돌 0). YYYYYNNN. **마지막 Y**.

**답 후보**: 1 ~ max(stones).

```java
public int stoneBridge(int[] stones, int k) {
    int lo = 1, hi = 0;
    for (int s : stones) hi = Math.max(hi, s);

    while (lo < hi) {
        int mid = lo + (hi - lo + 1) / 2;
        if (canCross(stones, k, mid)) lo = mid;
        else                          hi = mid - 1;
    }
    return lo;
}

// X 명이 건널 때: stones[i] < X 인 돌은 못 밟음. 연속 못 밟는 돌 K개 이상이면 false.
private boolean canCross(int[] stones, int k, int x) {
    int zeros = 0;
    for (int s : stones) {
        if (s < x) {
            zeros++;
            if (zeros >= k) return false;
        } else {
            zeros = 0;
        }
    }
    return true;
}
```

```kotlin
fun stoneBridge(stones: IntArray, k: Int): Int {
    var lo = 1; var hi = stones.max()
    while (lo < hi) {
        val mid = lo + (hi - lo + 1) / 2
        if (canCross(stones, k, mid)) lo = mid else hi = mid - 1
    }
    return lo
}

private fun canCross(stones: IntArray, k: Int, x: Int): Boolean {
    var zeros = 0
    for (s in stones) {
        if (s < x) {
            zeros++
            if (zeros >= k) return false
        } else {
            zeros = 0
        }
    }
    return true
}
```

**복잡도**: O(N log M).

**함정**:
- "마지막 Y" → `lo = mid` 패턴, mid 상위 반올림.
- `s < x` (`<=` 아님) — x 명이 건널 때 stones[i] = x 는 마지막 한 명까지 사용 가능.
- 슬라이딩 윈도우 (윈도우 K 내 max) O(N log K) 풀이도 있지만 parametric 이 더 직관.

---

## 7. 함정·엣지케이스

### 7.1 Overflow

| 위치 | 위험 | 방어 |
|---|---|---|
| `mid = (lo + hi) / 2` | lo + hi 가 INT_MAX 넘으면 음수 | `lo + (hi - lo) / 2` 또는 `(lo + hi) >>> 1` |
| Koko `hours += ceil(p/k)` | 누적 시간 long 필요 | hours 를 long, 조기 종료 |
| Split Array sum | 합이 INT_MAX 넘음 | long |
| 입국심사 hi = max × N | 10⁹ × 10⁹ | long |
| ceil 계산 `(p+k-1)/k` | p + k - 1 overflow | 가능하면 long, 또는 `p/k + (p%k!=0?1:0)` |

**경험칙**: parametric search 의 결정 함수에서 누적값 (sum, count, hours) 은 **무조건 long 으로 시작**. int 가 충분해도 long 으로 짜는 게 안전 마진. 라이브 코딩에서 면접관에게 "여기 long 인 이유는 누적 overflow 방지" 라고 한 줄 말하면 좋은 인상.

### 7.2 lower_bound vs upper_bound 혼동

```
[1, 2, 2, 2, 3]
lower_bound(2) = 1   ─┐
upper_bound(2) = 4   ─┴─ count(2) = 4 - 1 = 3

target 부재 시:
lower_bound(2.5) = 4 (insertion point)
upper_bound(2.5) = 4 (동일)
→ "target 존재?" = lower_bound(t) < n && arr[lower_bound(t)] == t
```

면접관이 "중복 원소가 있을 때 어느 index 가 나오나요?" 묻는 게 단골. `Arrays.binarySearch` 는 **보장 없음** (어느 거든 발견 시 반환). 정확한 의도가 있으면 lower/upper 직접 구현.

### 7.3 회전 배열의 pivot

```
회전 0번:  [1, 2, 3, 4, 5]      → arr[0] < arr[n-1], 그냥 정렬
회전 1번:  [5, 1, 2, 3, 4]      → arr[0] > arr[n-1]
회전 n-1번:[2, 3, 4, 5, 1]      → arr[0] > arr[n-1]
회전 n번:  [1, 2, 3, 4, 5]      → 다시 회전 0번과 같음
```

**중복 있으면 함정 폭증** (LC 154): `[2, 2, 2, 0, 1, 2]` → `arr[lo] == arr[mid] == arr[hi] = 2` 면 어느 쪽이 정렬됐는지 판단 불가. → `lo++, hi--` 한 칸씩 좁히기 → worst O(N). 면접관이 "중복 있을 때?" 꼬리질문 단골.

**회전 횟수 모를 때**: 일반적으로 모름 — 한 번 회전이라는 가정만. 답이 회전 점 (= 최솟값 index) 을 굳이 명시적으로 찾을 필요 없음 (LC 33 처럼 정렬된 절반 판단으로 충분). LC 153 처럼 명시적으로 찾아야 하면 별도 풀이.

### 7.4 Parametric 결정 함수 단조성 증명

이게 가장 중요한 함정. 면접관이 **"왜 단조인가요?"** 를 반드시 묻는다. 증명을 미리 머릿속에 정리해야 한다.

**Koko**: K↑ 면 모든 더미에서 `ceil(p/K)` 감소 (또는 동일) → 총 hours 감소 → H 이내로 더 잘 들어감 → feasible. 한 변수가 증가하면 결정 함수가 한 방향으로만 변함 → 단조.

**Split Array**: limit↑ 면 각 partition 이 더 많이 담을 수 있음 → 필요 partition 수 감소 (또는 동일) → "K 이하" 더 잘 만족 → feasible. 동일 논리.

**입국심사**: T↑ 면 각 심사관이 처리 가능한 인원 `T/times[i]`↑ → 총 처리 인원↑ → N 이상 더 잘 만족. 단조 증가.

**징검다리 건너기 ("마지막 Y" 변형)**: 인원 X↑ 면 더 많은 돌이 0 으로 변함 → 연속 K 0 발생 가능성↑ → feasible 가 깨짐. 단조 감소 함수의 마지막 Y 를 찾는 패턴.

**경계 예외**: 단조성이 깨지는 비단조 함수 (예: 어떤 X 에서는 Y → N → Y 반복) 에는 이분 탐색 불가. parametric search 적용 전에 항상 "X 가 한 방향으로 변할 때 결정이 한 방향으로만 변하는가?" 를 1초 안에 검증.

### 7.5 빈 배열 / 단일 원소

```java
// 빈 배열
new int[]{}: lo=0, hi=-1 (length-1) → while(lo<=hi) 안 들어감 → -1 정답
new int[]{}: lo=0, hi=0 (length) → while(lo<hi) 안 들어감 → 0 반환 (lower_bound)

// 단일 원소
new int[]{5}: target=5 → lo=0, hi=0, mid=0, 매치, return 0
new int[]{5}: target=3 → lo=0, hi=0, mid=0, 5>3, hi=-1, return -1 (패턴 A)
                       또는 → lo=0, hi=1, mid=0, 5>3, hi=0, return 0 (패턴 B lower_bound)
```

**경계 입력은 항상 가장 먼저 머릿속에서 돌려본다**. 면접관이 "빈 입력은요?" 묻기 전에 한 줄 코멘트로 짚으면 가산점.

### 7.6 ternary search 와의 혼동

```
[binary]       [ternary]
단조 함수       단봉 함수 (unimodal)
f: 0→1 한 방향  f: 증가 → 정점 → 감소
mid 1개         m1, m2 두 개 (1/3, 2/3 지점)
log₂N           log₁.₅N  (느림)
```

ternary search 는 단봉 함수 (unimodal) 의 정점을 찾는 알고리즘. binary 의 친척이지만 한국 라이브 코딩 테스트에서는 거의 안 나옴. 면접관이 "ternary search 도 있죠?" 묻기만 함 → "예, 단봉 함수에 쓰지만 단조 함수면 binary 가 더 빠릅니다" 정도 답변.

LC 162 peak finding 도 사실 단봉이지만, 양 끝 -∞ 가정 덕분에 binary 로 처리됨.

---

## 8. 꼬리질문 트리

**Q1. ternary search 와 binary search 의 차이는?**
> binary 는 단조 함수의 임계점, ternary 는 단봉 함수의 정점. ternary 는 매 step 2/3 만 좁혀서 log₁.₅N (느림). 단조면 binary, 단봉이면 ternary. 단, 정수 ternary 는 mid1/mid2 가 같아질 때 무한 루프 주의 — 보통 마지막 3 원소를 brute force 처리.

**Q2. decision function 이 단조라는 증명을 어떻게 하나요?**
> "변수 X 가 증가할 때 함수값이 한 방향으로만 변함" 을 식으로 보이거나 구조적으로 보임. 예: Koko 는 `hours(K) = Σ ceil(p_i/K)` 이고 `ceil(p/K)` 는 K 에 대해 단조 감소 (정수 나눗셈 성질) → 합도 단조 감소. 그러면 `hours(K) ≤ H` 는 K 에 대해 단조 증가 (NNNYY 패턴). 면접에서 증명을 1~2줄로 정리해서 미리 외우는 게 좋음.

**Q3. 회전 횟수를 모를 때는?**
> 회전 횟수는 사실 LC 33 풀이에 필요 없음 — 매 step 의 두 절반 중 정렬된 쪽만 알면 됨. 명시적으로 회전점 (= 최솟값 index) 을 알고 싶으면 LC 153 풀이를 따로 돌리고, 그걸로 배열을 두 정렬 절반으로 나눈 후 각각에 표준 binary search. 두 방법 모두 O(log N).

**Q4. 2D matrix 의 binary search 는?**
> 두 종류. (1) **각 행 정렬 + 행 첫 원소 정렬** (LC 74) — 1D 로 펼쳐서 단일 binary, O(log MN). (2) **각 행/열 모두 정렬되지만 전체 정렬 아님** (LC 240) — 오른쪽 위에서 시작해 매 step 한 줄 또는 한 칸 좁힘, O(M+N). 후자는 엄밀히는 binary search 아니지만 같은 "단조성 활용" 가족.

**Q5. parametric search vs DP — 언제 어느 걸?**
> parametric 은 "답 후보 범위 + 결정 함수" 가 보일 때, DP 는 "부분 문제 정의 + 점화식" 이 보일 때. Split Array (LC 410) 는 둘 다 가능: DP O(N²K), parametric O(N log S). 입력 N=10³, K=50 이면 둘 다 OK, N=10⁵면 parametric 만. 일반적으로 parametric 이 더 빠른 경우가 많음 (log 곱이라 K 가 클수록 유리).

**Q6. floating point parametric search 가능한가요?**
> 가능. 종료 조건이 `hi - lo > 1e-9` 같은 epsilon. 단, 부동 소수 오차로 무한 루프 가능 → step 횟수 상한 (`for i in 0..100`) 으로 강제 종료. 예: "최대 둘레가 X 이상인 정삼각형의 최대 X" 같은 연속값 답.

**Q7. binary search 가 log N 인데 hash 는 O(1). hash 가 항상 우월?**
> 아니오. (1) hash 는 평균 O(1), worst O(N) (flooding). binary 는 worst O(log N). (2) hash 는 "정확한 key" 만 찾음. binary 는 "lower/upper bound" 가능. (3) hash 는 정렬 불가 → range query 불가. binary 는 sorted 면 range query O(log N + k). DB index 가 B-tree (binary 친척) 인 이유 — equality + range 둘 다.

**Q8. JDK Arrays.binarySearch 의 음수 반환 의미는?**
> `-(insertion point) - 1`. 못 찾으면 음수, 절댓값에서 1 빼면 lower_bound. 왜 이런 인코딩? 음수 = "못 찾음" 신호 + 동시에 삽입 위치 정보 전달. 0 만 음수로 못 만드니까 `-1` shift. C++ `lower_bound` 는 직접 index 반환 — Java 가 더 정보가 많지만 직관적이진 않음.

---

## 9. 다른 패턴과의 연결

### 9.1 정렬 + Binary Search vs Two Pointer

```
[정렬된 배열에서 합 = target 인 쌍]

Two Pointer (Ch 01):   O(N)        ─ 두 포인터 양쪽에서 좁힘
Binary Search:         O(N log N)  ─ 각 원소마다 complement 를 이분 탐색
                                     (단, 배열 정렬돼 있어도 같은 결과)

[정렬 안 됨]
Hash Set:              O(N)        ─ complement 를 set 에서 찾음 (Ch 05 hashing)
정렬 + Two Pointer:    O(N log N)  ─ 일단 정렬 후
정렬 + Binary Search:  O(N log N)  ─ 마찬가지
```

→ 같은 문제에 여러 패턴 적용 가능. **trade-off**: hash 는 추가 메모리 O(N), binary search 는 정렬 비용. 입력 이미 정렬됐으면 two pointer 가 더 깔끔, 정렬 안 됐으면 hash 가 더 빠름. 면접에서 multiple approach 비교는 좋은 인상.

### 9.2 LIS — Longest Increasing Subsequence O(N log N)

```
DP 풀이:  O(N²)   ─ 각 i 에서 dp[i] = max(dp[j]) + 1, j < i, arr[j] < arr[i]
이분 탐색: O(N log N)
   tails[]: 길이 l 인 IS 의 가능한 가장 작은 끝 원소
   매 원소 x: tails 에서 lower_bound(x) 위치를 x 로 교체
   tails.size() 가 답
```

```java
public int lengthOfLIS(int[] nums) {
    int[] tails = new int[nums.length];
    int size = 0;
    for (int x : nums) {
        int lo = 0, hi = size;
        while (lo < hi) {                 // lower_bound
            int mid = lo + (hi - lo) / 2;
            if (tails[mid] < x) lo = mid + 1;
            else                hi = mid;
        }
        tails[lo] = x;
        if (lo == size) size++;
    }
    return size;
}
```

이 알고리즘은 **lower_bound 의 가장 우아한 응용** 중 하나. DP 단순 풀이에서 binary search 를 끼워 한 자릿수 차이 (10⁴ vs 10⁶ 처리) 를 만든다. LIS 자체는 DP 챕터에서 다루지만 binary search 의 위력을 보여주는 사례.

### 9.3 DB B-tree Index

```
[PostgreSQL B-tree 인덱스]
                     [50 | 100]                  ← root, fanout=N (보통 ~250)
                    /     |     \
              [10|30]  [60|80]  [120|150]        ← internal nodes
             /  |  \   /  |  \    ...
          [leaf rows ...]                        ← leaf, 실제 row pointer

WHERE id = 75
  → root 에서 "50 ≤ 75 < 100" 절반 선택
  → [60|80] 에서 "60 ≤ 75 < 80" 절반 선택
  → leaf 에서 binary search
  
N = 10억 row, fanout=250 → 깊이 4~5
  → disk seek 5번에 row 찾기  (full scan = 10억 read)
```

B-tree 의 매 node 는 정렬된 key 배열 → 그 안에서 binary search. 트리 깊이는 log_fanout(N). DB index 가 빠른 이유 = **binary search 의 disk 친화 변형**. 시니어가 EXPLAIN 을 보고 "왜 index seek 가 빠른지" 즉답 가능해야 함.

### 9.4 Sorted Log File 탐색

```
[운영 시나리오: 10GB access log 에서 특정 timestamp 이후 첫 라인 찾기]

선형 탐색:  10GB sequential read = 수 분
Binary search by file offset:
  lo=0, hi=10GB
  mid = (lo+hi)/2  ─ seek to mid, 다음 newline 까지 읽음
  그 라인의 timestamp 비교 → 절반 좁힘
  → log₂(10GB) ≈ 33 step, 각 step disk seek + 한 줄 read
  → 1초 미만 완료

→ Linux `look` 명령어, journalctl `--since` 가 내부적으로 이 알고리즘
```

운영 환경에서 정렬된 파일/로그 검색은 binary search 의 자연 응용. timestamp 가 단조 증가하면 file offset 으로 이분 탐색 가능. 시니어가 "왜 이 로그 검색이 빠른가?" 답변 가능한 수준.

### 9.5 시간 기반 캐시 만료 검색

```
[Redis sorted set 으로 expire time 관리]

ZADD expirations <timestamp> <key>      ─ 정렬된 set 에 추가
ZRANGEBYSCORE expirations 0 NOW         ─ NOW 이하 timestamp 의 key 들
   ─ 내부적으로 skip list 의 lower_bound 같은 동작
   ─ O(log N + M), M = 만료된 개수

→ 매 초마다 만료 cleanup, 10^7 cache 에서도 log 시간
```

Redis sorted set (skip list) 의 ZRANGEBYSCORE 는 binary search 의 확률적 친척 (skip list = 확률적 balanced tree). 시간 기반 캐시 만료, leaderboard, geo-index 가 동일 패턴.

### 9.6 Production 진단 사고 패턴

| 증상 | 의심 | 진단 | 해결 |
|---|---|---|---|
| 정렬된 큰 데이터 lookup 느림 | linear scan 사용 중 | 코드 리뷰, profile | binary search 또는 hash 도입 |
| DB index seek 인데 느림 | index 안 탐 (cast/function) | EXPLAIN ANALYZE | index 친화적 쿼리로 |
| parametric 문제를 brute force 로 풀고 있음 | log 곱 안 보임 | 답 후보 범위 단조성 확인 | parametric search 도입 |
| log 파일 grep 수 분 | sequential scan | timestamp 기반 정렬? | binary search by offset, journalctl `--since` |
| Redis ZSET cleanup 느림 | full scan | ZRANGEBYSCORE 미사용 | 정렬된 set + range query |

### 9.7 마스터의 한 줄 요약

> "정렬된 배열에서 값 찾기" 만 보는 사람은 입문자.
> 마스터는 단조성이 보이는 모든 문제 — 배열, 행렬, 결정 함수, 시간축, file offset, DB index, skip list — 에 같은 이분 탐색 골격을 적용한다.
> **본질은 단조성, 도구는 log N, 적용 범위는 백지에서 그릴 수 있는 모든 단조 함수.**

---

## 10. 백지 마스터 체크리스트

이 챕터를 닫기 전에 다음을 백지에서 해본다.

- [ ] 표준 binary search 패턴 A (lo ≤ hi) Java/Kotlin 양쪽
- [ ] lower_bound 패턴 B (lo < hi, hi = mid) Java/Kotlin 양쪽
- [ ] upper_bound — 부등호 한 글자 차이
- [ ] 회전 배열 search — "정렬된 절반" 판정 분기 4갈래
- [ ] Find Minimum in Rotated — `arr[hi]` 와 비교하는 이유
- [ ] Find Peak — 정렬 안 된 배열인데 log 인 이유 (양 끝 -∞)
- [ ] Koko — 결정 함수 단조성 증명 1줄, hours long 이유
- [ ] Split Array — 답 후보 lo=max(arr), hi=sum(arr) 이유
- [ ] 입국심사 / 징검다리 — "마지막 Y" 찾기, lo=mid + mid 상위 반올림
- [ ] (lo+hi)/2 overflow 가 위험한 경우 — Joshua Bloch 2006 일화
- [ ] DB B-tree index 가 왜 fast (binary search + disk page locality)
- [ ] LIS O(N log N) 의 tails 배열 + lower_bound 트릭

12개 모두 즉답 가능하면 이 챕터 마스터.

---

> 이분 탐색이라는 단어를 들었을 때 머릿속에 자동으로 떠올라야 한다: 단조성 + lo/hi 좁히기 + lower/upper bound 한 글자 차이 + 회전 배열의 정렬된 절반 + parametric 의 결정 함수 + log N 의 production 의미 (B-tree, sorted log, Redis ZSET). 이게 시니어가 binary search 를 "안다" 는 의미다.
