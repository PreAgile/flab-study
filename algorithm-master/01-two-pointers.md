# 01. Two Pointers (투포인터)

> "투포인터? 양쪽에서 좁혀오는 거"라고 답하면 입문자.
> 마스터는 **왜 정렬이 전제로 깔리는지**, **왜 O(n²) brute force가 O(n)으로 무너지는지**, **왜 in-place 수정 문제는 거의 항상 fast/slow 변형으로 풀리는지**, **Dutch national flag 3-pointer가 quicksort의 partition과 같은 뿌리인지**까지 본다.
>
> 이 문서는 외울 코드 스니펫이 아니라 **본질·왜·언제·연결**을 다룬다. 백지에서 6가지 변형(양 끝 좁히기 / fast-slow / in-place 삭제 / 3-pointer / 문자열 회문 / k-sum)을 그릴 수 있어야 한다.

---

## 0. 인지 신호 — 30초 안에 "투포인터구나" 감지하기

문제 설명을 읽었을 때 다음 키워드/패턴이 하나라도 등장하면 투포인터를 먼저 의심한다.

| 신호 | 예시 표현 | 왜 투포인터인가 |
|---|---|---|
| **정렬된 배열에서 합·차·쌍** | "sorted array에서 두 수를 더해 target", "두 수의 차이가 가장 작은" | 양 끝에서 합/차 단조성을 이용해 한쪽 포인터를 결정적으로 이동 |
| **in-place 수정 / O(1) 메모리** | "remove duplicates in-place", "0을 모두 뒤로", "추가 배열 사용 금지" | write 포인터 + read 포인터 (fast/slow)로 한 번의 스캔에 끝 |
| **양 끝에서 좁혀오는 조건** | "max area", "가장 긴 회문 부분 문자열", "container with most water" | 결과가 양 끝의 함수이고 한쪽을 움직일 때 단조 감소/증가가 보장 |
| **3개 이상의 값 분류** | "0/1/2만 정렬", "음수/0/양수 분리" | 3-way partition (Dutch flag) — `low/mid/high` 3포인터 |
| **회문·반전·대칭** | "valid palindrome", "reverse vowels" | `left ← →` 동시 진행으로 대칭성 검사 |
| **두 정렬된 시퀀스 병합·비교** | "merge sorted arrays", "intersection of two sorted arrays" | 각 배열에 포인터 하나씩, 작은 쪽을 전진 |

**역으로 투포인터 아님 신호**: 입력이 정렬돼 있지 않고 **정렬 비용이 결과에 영향을 미치는 경우**(예: 원래 인덱스를 그대로 반환해야 하는 Two Sum I) → HashMap이 정답. 그래서 LeetCode 1번 (Two Sum)은 **HashMap 문제**, 167번 (Two Sum II — sorted)은 **투포인터 문제**다. 정렬 여부가 갈림길.

---

## 1. 백지 그리기 — 6가지 변형의 ASCII 지도

투포인터는 단일 패턴이 아니라 **포인터 배치 + 이동 규칙의 패밀리**다. 백지에서 다음 6장을 그릴 수 있어야 한다.

### 1.1 양 끝 좁히기 (Opposite Ends, Converging)

정렬된 배열에서 합·차·면적·회문에 쓰는 기본형.

```
   [ 2,  3,  5,  7, 11, 13, 17, 19, 23 ]    target = 26
     ↑                                ↑
    left                            right
     │                                │
     │  sum = 2 + 23 = 25 < 26  → left++ (작은 쪽을 키워야 함)
     │
   [ 2,  3,  5,  7, 11, 13, 17, 19, 23 ]
         ↑                            ↑
        left                        right
            sum = 3 + 23 = 26 ✓  → 정답
```

핵심 **단조성**: 정렬돼 있으니 `sum < target`일 때 `right--`는 자살(더 작아짐), `left++`만 유효. 반대로 `sum > target`은 `right--`만 유효. 한쪽 포인터 이동이 **결정적**이라서 O(n).

### 1.2 같은 방향 / Fast-Slow (Same Direction)

in-place 수정, cycle 검출, 윈도우 압축에 쓴다.

```
   read 포인터(빠름)  →  배열을 끝까지 스캔
   write 포인터(느림) →  유지할 값만 받음

   [ 1, 1, 2, 2, 3, 4, 4 ]
     ↑↑
     wr
     rd

   rd 진행 → 새 값 만나면 wr 위치에 쓰고 wr++
   rd 진행 → 중복이면 wr 그대로

   결과: [ 1, 2, 3, 4, _, _, _ ]
                       ↑
                      wr (= 새로운 길이)
```

`slow`는 "지금까지 만든 결과의 끝", `fast`는 "탐색 커서". 두 포인터가 같은 방향으로 다른 속도로 간다고 해서 fast-slow.

### 1.3 In-place 삭제 / 분리 (Two-Pass vs One-Pass)

```
   "0을 뒤로 보내기" (LeetCode 283)
   [ 0, 1, 0, 3, 12 ]
     ↑
     wr/rd

   rd 진행, nonzero 만나면 arr[wr++] = arr[rd]
   rd 끝나면 wr ~ 끝까지 0 채움

   wr 진행:    [ 1, 3, 12, _, _ ]
   0 채움:     [ 1, 3, 12, 0, 0 ]
```

### 1.4 3-Pointer / Dutch National Flag

값을 3개 부류로 분할. quicksort 3-way partition과 같은 뿌리.

```
   목표: [ 0...0 | 1...1 | 2...2 ]
            low ↑   mid ↑   high ↑

   초기:  low = mid = 0,  high = n-1
   while (mid <= high):
       arr[mid] == 0  →  swap(low, mid), low++, mid++
       arr[mid] == 1  →  mid++
       arr[mid] == 2  →  swap(mid, high), high--    (mid는 그대로 — 새 값 검사 필요)
```

```
   [ 2, 0, 2, 1, 1, 0 ]
     L  M           H

   arr[M]=2 → swap M,H → [ 0, 0, 2, 1, 1, 2 ],  H--
                            L  M        H
   arr[M]=0 → swap L,M → [ 0, 0, 2, 1, 1, 2 ],  L++, M++
                              L  M     H
   ... 진행 ...
   최종: [ 0, 0, 1, 1, 2, 2 ]
```

### 1.5 회문 / 대칭 검사

```
   "A man, a plan, a canal: Panama"
   정제 후: "amanaplanacanalpanama"
            ↑                   ↑
            L                   R
   while L < R:
       if s[L] != s[R] → false
       L++, R--
```

### 1.6 두 정렬 시퀀스 병합

```
   A = [ 1, 3, 5, 7 ]      B = [ 2, 4, 6 ]
        ↑                       ↑
        i                       j

   if A[i] <= B[j]: out << A[i++]
   else:             out << B[j++]
   (한쪽 끝나면 나머지 flush)
```

이 6장이 머릿속에 있으면 신호만 보고 즉시 변형을 선택할 수 있다.

---

## 2. 직관과 정의

### 2.1 한 줄 비유

**"양쪽에서 가운데로 좁혀오는 협상 테이블, 또는 같은 방향으로 다른 속도로 달리는 두 주자."**

### 2.2 정확한 정의

투포인터는 **선형 자료구조(배열·문자열·연결 리스트)를 두 개의 인덱스/포인터로 동시에 훑으며, 한 포인터의 이동 결정이 단조적 조건에 따라 정해지는** 패턴이다. brute force가 `O(n²)`인 모든 쌍을 검사하는 데 비해, 단조성 덕분에 **각 포인터가 최대 n번만 움직여 총 O(n)**으로 줄어든다.

### 2.3 정렬이 왜 전제가 되는가

양 끝 좁히기에서 `left++`/`right--` 결정이 옳다고 확신하려면 **"버려진 절반에 더 좋은 답이 없다"**는 보장이 필요하다. 정렬은 이 보장을 준다.

예: `arr[left] + arr[right] < target`일 때 `right--`를 하면, `right` 위치는 `arr[left]`와 짝지을 수 있는 **가장 큰 값**이었으므로 `left`를 이 위치 이전과 짝짓는 모든 경우는 이미 `< target`이다. 그래서 `left++`만 유효 — 정렬이 없으면 이 추론 자체가 깨진다.

### 2.4 정렬이 필요 없는 경우

- **Fast-slow (in-place 수정)**: 원소를 분류·이동만 할 뿐 비교 단조성이 필요 없음 → 정렬 불필요.
- **회문 검사**: 대칭성만 보면 됨.
- **연결 리스트 cycle 검출** (Floyd): 토끼-거북이 거리만 본다.
- **3-way partition**: 값이 0/1/2처럼 **이미 fixed range**라 정렬 자체가 목표 (정렬을 만드는 알고리즘).

**시니어 운영 관점**: 정렬 비용 `O(n log n)`이 결과 복잡도를 지배하는지 항상 확인. 입력이 이미 정렬돼 들어오면 (예: DB가 sorted index를 가짐) 투포인터는 그대로 `O(n)`. 안 그러면 `O(n log n)`. DB index range query가 정렬 가정 위에서 binary scan을 빠르게 하는 것과 같은 원리 — **정렬은 비용이 아니라 자산**.

---

## 3. Java 템플릿

### 3.1 양 끝 좁히기 (Opposite Ends)

```java
import java.util.*;

class Solution {
    // 정렬된 arr에서 두 수의 합이 target인 인덱스 쌍 반환
    public int[] twoSumSorted(int[] arr, int target) {
        int left = 0, right = arr.length - 1;
        while (left < right) {
            // 주의: int + int overflow 가능 → long 캐스팅 권장
            long sum = (long) arr[left] + arr[right];
            if (sum == target) return new int[]{left, right};
            else if (sum < target) left++;   // 합을 키워야 함
            else                    right--; // 합을 줄여야 함
        }
        return new int[]{-1, -1};
    }
}
```

### 3.2 같은 방향 / Fast-Slow (in-place 중복 제거)

```java
class Solution {
    // 정렬된 배열에서 중복을 제거하고 새 길이 반환 (in-place)
    public int removeDuplicates(int[] nums) {
        if (nums.length == 0) return 0;
        int write = 1; // 첫 원소는 항상 유지
        for (int read = 1; read < nums.length; read++) {
            if (nums[read] != nums[read - 1]) {
                nums[write++] = nums[read];
            }
        }
        return write;
    }
}
```

### 3.3 In-place 분리 (0을 뒤로)

```java
class Solution {
    // 0을 모두 배열 뒤로, nonzero의 상대 순서 유지 (in-place)
    public void moveZeroes(int[] nums) {
        int write = 0;
        for (int read = 0; read < nums.length; read++) {
            if (nums[read] != 0) {
                // swap 대신 단순 대입 → write < read이면 read 위치는 곧 덮일 0
                int tmp = nums[write];
                nums[write] = nums[read];
                nums[read] = tmp;
                write++;
            }
        }
    }
}
```

### 3.4 3-Pointer (Dutch National Flag)

```java
class Solution {
    // 0/1/2만 들어있는 배열을 in-place 정렬
    public void sortColors(int[] nums) {
        int low = 0, mid = 0, high = nums.length - 1;
        while (mid <= high) {
            switch (nums[mid]) {
                case 0:
                    swap(nums, low++, mid++);
                    break;
                case 1:
                    mid++;
                    break;
                case 2:
                    swap(nums, mid, high--);
                    // mid는 증가시키지 않음 — 방금 받은 값은 미검사
                    break;
            }
        }
    }
    private void swap(int[] a, int i, int j) {
        int t = a[i]; a[i] = a[j]; a[j] = t;
    }
}
```

### 3.5 K-Sum 일반화 (3Sum 기준)

```java
import java.util.*;

class Solution {
    public List<List<Integer>> threeSum(int[] nums) {
        Arrays.sort(nums);
        List<List<Integer>> res = new ArrayList<>();
        int n = nums.length;
        for (int i = 0; i < n - 2; i++) {
            if (nums[i] > 0) break;                 // 정렬 후 음수 영역 끝나면 합 0 불가능
            if (i > 0 && nums[i] == nums[i - 1]) continue; // i 중복 skip
            int left = i + 1, right = n - 1;
            while (left < right) {
                int sum = nums[i] + nums[left] + nums[right];
                if (sum == 0) {
                    res.add(Arrays.asList(nums[i], nums[left], nums[right]));
                    left++; right--;
                    while (left < right && nums[left] == nums[left - 1]) left++;   // left 중복 skip
                    while (left < right && nums[right] == nums[right + 1]) right--; // right 중복 skip
                } else if (sum < 0) left++;
                else right--;
            }
        }
        return res;
    }
}
```

---

## 4. Kotlin 템플릿

### 4.1 양 끝 좁히기

```kotlin
class Solution {
    fun twoSumSorted(arr: IntArray, target: Int): IntArray {
        var left = 0
        var right = arr.size - 1
        while (left < right) {
            val sum = arr[left].toLong() + arr[right]
            when {
                sum == target.toLong() -> return intArrayOf(left, right)
                sum < target           -> left++
                else                   -> right--
            }
        }
        return intArrayOf(-1, -1)
    }
}
```

### 4.2 Fast-Slow

```kotlin
class Solution {
    fun removeDuplicates(nums: IntArray): Int {
        if (nums.isEmpty()) return 0
        var write = 1
        for (read in 1 until nums.size) {
            if (nums[read] != nums[read - 1]) {
                nums[write++] = nums[read]
            }
        }
        return write
    }
}
```

### 4.3 In-place 분리

```kotlin
class Solution {
    fun moveZeroes(nums: IntArray): Unit {
        var write = 0
        for (read in nums.indices) {
            if (nums[read] != 0) {
                val tmp = nums[write]
                nums[write] = nums[read]
                nums[read] = tmp
                write++
            }
        }
    }
}
```

### 4.4 Dutch Flag

```kotlin
class Solution {
    fun sortColors(nums: IntArray): Unit {
        var low = 0
        var mid = 0
        var high = nums.size - 1
        while (mid <= high) {
            when (nums[mid]) {
                0 -> { swap(nums, low++, mid++) }
                1 -> { mid++ }
                2 -> { swap(nums, mid, high--) }
            }
        }
    }
    private fun swap(a: IntArray, i: Int, j: Int) {
        val t = a[i]; a[i] = a[j]; a[j] = t
    }
}
```

### 4.5 3Sum

```kotlin
class Solution {
    fun threeSum(nums: IntArray): List<List<Int>> {
        nums.sort()
        val res = mutableListOf<List<Int>>()
        for (i in 0 until nums.size - 2) {
            if (nums[i] > 0) break
            if (i > 0 && nums[i] == nums[i - 1]) continue
            var left = i + 1
            var right = nums.size - 1
            while (left < right) {
                val sum = nums[i] + nums[left] + nums[right]
                when {
                    sum == 0 -> {
                        res.add(listOf(nums[i], nums[left], nums[right]))
                        left++; right--
                        while (left < right && nums[left] == nums[left - 1]) left++
                        while (left < right && nums[right] == nums[right + 1]) right--
                    }
                    sum < 0  -> left++
                    else     -> right--
                }
            }
        }
        return res
    }
}
```

Kotlin 관용 표현 포인트:
- `when` 표현식으로 분기 가독성 ↑
- `IntArray.indices`, `until` range로 boundary 명료
- `nums.sort()` 는 in-place (Java의 `Arrays.sort(nums)`와 동일)
- 반환 `Unit`은 명시 안 해도 됨, 그러나 LeetCode 시그니처는 그대로 유지

---

## 5. 시간/공간 복잡도 — 왜 그런지

### 5.1 양 끝 좁히기

```
   left 0 → ...                → n-1
   right n-1 → ...             → 0
   매 iteration마다 left++ 또는 right-- (둘 다 발생 안 함)
   → 두 포인터 합쳐서 최대 n번 이동
   → 시간 O(n)
   → 공간 O(1) (인덱스 두 개)
```

정렬이 필요한 경우 정렬 비용 `O(n log n)`이 지배 → **전체 O(n log n)**.

### 5.2 Fast-slow / in-place

`read`가 0→n-1로 한 번만 진행, `write`는 `read`보다 항상 작거나 같음. `read`만 n번 → **O(n) 시간, O(1) 공간**.

### 5.3 3Sum

```
   외부 for i: n번
   내부 left/right while: 각 i마다 O(n)
   → O(n²)
   정렬은 O(n log n) — n² 안에 묻힘
   → 전체 O(n²) 시간, O(1) 보조 공간 (결과 리스트 제외)
```

K-Sum 일반화: K개의 수 → `O(n^(K-1))`. 4Sum은 `O(n³)`.

### 5.4 Dutch Flag

```
   mid는 단조 증가 또는 high가 감소 (case 2일 때)
   mid + (n-1 - high) 합이 매 iteration마다 1씩 증가
   → 최대 n iteration
   → O(n) 시간, O(1) 공간
```

quicksort의 3-way partition은 같은 원리로 **중복 키가 많을 때 일반 quicksort보다 빨라진다** (Bentley-McIlroy 1993). 코딩 테스트의 Dutch flag는 단독 문제로 보이지만, 실은 quicksort 내부 루틴.

### 5.5 정렬 비용 vs HashMap

| 접근 | 시간 | 공간 | 언제 |
|---|---|---|---|
| brute force 모든 쌍 | O(n²) | O(1) | 작은 n |
| HashMap (Two Sum I) | O(n) | O(n) | 입력 정렬 안 됨, 원래 인덱스 필요 |
| 정렬 + 투포인터 | O(n log n) | O(1) 또는 O(n) (정렬 안정성 위해) | 추가 메모리 제약, 정렬 가능 |

**시니어 운영 관점**: O(n) 시간이라고 다 좋은 게 아니다. HashMap은 캐시 미스, GC 압박, hash 충돌 risk가 있다. 정렬+투포인터는 cache locality가 좋고 worst case도 안정적 (no flooding risk). 대용량 batch 처리에서는 후자가 더 빠른 경우가 많다 — DB가 sort-merge join을 hash join보다 선호하는 상황(메모리 부족, 결과가 sorted여야 함)과 같은 trade-off.

---

## 6. 대표 문제

### 6.1 LeetCode 167 — Two Sum II - Input Array Is Sorted

**한국어 요약**: 1-indexed 정렬된 배열 `numbers`에서 두 수의 합이 `target`이 되는 두 인덱스를 반환. 정확히 하나의 답이 존재하며 같은 원소를 두 번 쓸 수 없음. O(1) 추가 메모리.

**접근**: 입력이 정렬돼 있고 O(1) 메모리 제약 → HashMap 불가 → 양 끝 좁히기.

**Java 풀이**:
```java
import java.util.*;

class Solution {
    public int[] twoSum(int[] numbers, int target) {
        int left = 0, right = numbers.length - 1;
        while (left < right) {
            long sum = (long) numbers[left] + numbers[right];
            if (sum == target) {
                return new int[]{left + 1, right + 1}; // 1-indexed
            } else if (sum < target) {
                left++;
            } else {
                right--;
            }
        }
        return new int[]{-1, -1};
    }
}
```

**Kotlin 풀이**:
```kotlin
class Solution {
    fun twoSum(numbers: IntArray, target: Int): IntArray {
        var left = 0
        var right = numbers.size - 1
        while (left < right) {
            val sum = numbers[left].toLong() + numbers[right]
            when {
                sum == target.toLong() -> return intArrayOf(left + 1, right + 1)
                sum < target           -> left++
                else                   -> right--
            }
        }
        return intArrayOf(-1, -1)
    }
}
```

**복잡도**: O(n) 시간, O(1) 공간.

**함정**:
- 1-indexed 반환 (LeetCode 시그니처). 0-indexed로 반환하면 wrong answer.
- `numbers[left] + numbers[right]` overflow — 각 원소가 `Integer.MAX_VALUE`에 가까우면 int 덧셈 overflow. **long 캐스팅 필수**.
- `left < right` (≤ 아님) — 같은 원소 재사용 금지.

---

### 6.2 LeetCode 15 — 3Sum

**한국어 요약**: 배열 `nums`에서 `a + b + c == 0`인 모든 **서로 다른** triplet을 반환. 결과 안 중복 없어야 함.

**접근**: 정렬 후 첫 원소 `i`를 고정하고 나머지 두 수는 양 끝 좁히기로 `target = -nums[i]`를 찾음. 중복 제거가 핵심.

**Java 풀이**:
```java
import java.util.*;

class Solution {
    public List<List<Integer>> threeSum(int[] nums) {
        Arrays.sort(nums);
        List<List<Integer>> res = new ArrayList<>();
        int n = nums.length;
        for (int i = 0; i < n - 2; i++) {
            if (nums[i] > 0) break;
            if (i > 0 && nums[i] == nums[i - 1]) continue;
            int left = i + 1, right = n - 1;
            while (left < right) {
                int sum = nums[i] + nums[left] + nums[right];
                if (sum == 0) {
                    res.add(Arrays.asList(nums[i], nums[left], nums[right]));
                    left++; right--;
                    while (left < right && nums[left] == nums[left - 1]) left++;
                    while (left < right && nums[right] == nums[right + 1]) right--;
                } else if (sum < 0) {
                    left++;
                } else {
                    right--;
                }
            }
        }
        return res;
    }
}
```

**Kotlin 풀이**:
```kotlin
class Solution {
    fun threeSum(nums: IntArray): List<List<Int>> {
        nums.sort()
        val res = mutableListOf<List<Int>>()
        val n = nums.size
        for (i in 0 until n - 2) {
            if (nums[i] > 0) break
            if (i > 0 && nums[i] == nums[i - 1]) continue
            var left = i + 1
            var right = n - 1
            while (left < right) {
                val sum = nums[i] + nums[left] + nums[right]
                when {
                    sum == 0 -> {
                        res.add(listOf(nums[i], nums[left], nums[right]))
                        left++; right--
                        while (left < right && nums[left] == nums[left - 1]) left++
                        while (left < right && nums[right] == nums[right + 1]) right--
                    }
                    sum < 0  -> left++
                    else     -> right--
                }
            }
        }
        return res
    }
}
```

**복잡도**: O(n²) 시간, O(1) 보조 공간 (결과 리스트 제외, 정렬도 in-place).

**함정**:
- **중복 처리**가 모든 위치 (i, left, right)에서 필요. 한 곳이라도 빠뜨리면 `[[0,0,0],[0,0,0]]` 같은 중복 답 발생.
- 정답 찾은 직후 `left++; right--`를 잊으면 무한 루프.
- 정렬 안 하면 양 끝 좁히기 단조성 깨짐 — 사용자 입력이 sorted라도 명시 안 됐으면 sort 호출.
- `nums[i] > 0` 가지치기: 정렬 후 첫 수가 양수면 나머지 둘도 양수 → 합 0 불가능, break.

---

### 6.3 LeetCode 11 — Container With Most Water

**한국어 요약**: 높이 배열 `height[]`에서 두 막대를 골라 만든 수조의 최대 넓이를 반환. 넓이 = `min(h[i], h[j]) * (j - i)`.

**접근**: 양 끝 좁히기. 더 짧은 막대를 안쪽으로 이동 — **이유**: 더 긴 쪽을 움직이면 폭은 줄고 높이도 `min`이 이미 짧은 쪽에 막혀 절대 늘어날 수 없음 → 짧은 쪽을 움직여야만 더 큰 답의 **가능성**이 생긴다.

**증명 스케치**: 폭 `(j - i)`는 매 step마다 1씩 줄어든다 (이미 손해). 그래서 높이는 반드시 늘어야 한다. `min(h[i], h[j])`를 늘리려면 짧은 쪽을 옮겨야 한다 — 긴 쪽을 옮기면 `min`은 그대로거나 더 작아진다.

**Java 풀이**:
```java
class Solution {
    public int maxArea(int[] height) {
        int left = 0, right = height.length - 1;
        int best = 0;
        while (left < right) {
            int h = Math.min(height[left], height[right]);
            int area = h * (right - left);
            if (area > best) best = area;
            // 더 짧은 막대를 안쪽으로 옮김
            if (height[left] < height[right]) left++;
            else                              right--;
        }
        return best;
    }
}
```

**Kotlin 풀이**:
```kotlin
class Solution {
    fun maxArea(height: IntArray): Int {
        var left = 0
        var right = height.size - 1
        var best = 0
        while (left < right) {
            val h = minOf(height[left], height[right])
            val area = h * (right - left)
            if (area > best) best = area
            if (height[left] < height[right]) left++ else right--
        }
        return best
    }
}
```

**복잡도**: O(n) 시간, O(1) 공간.

**함정**:
- "왜 짧은 쪽을 옮기는가?"는 면접 단골 꼬리질문. 위 증명을 답할 수 있어야 함.
- 동률일 때 (`height[left] == height[right]`) 어느 쪽을 옮겨도 됨 — 정답은 같다.
- brute force `O(n²)`는 작은 n에서는 통과되지만 LeetCode constraint (`n ≤ 10^5`) 에서는 TLE.

---

### 6.4 LeetCode 26 — Remove Duplicates from Sorted Array

**한국어 요약**: 정렬된 `nums`에서 중복을 in-place로 제거하고 unique 개수 k를 반환. `nums`의 앞 k개에 unique 값을 두면 됨.

**접근**: fast-slow. `write`는 다음으로 unique을 둘 자리, `read`는 스캔.

**Java 풀이**:
```java
class Solution {
    public int removeDuplicates(int[] nums) {
        if (nums.length == 0) return 0;
        int write = 1;
        for (int read = 1; read < nums.length; read++) {
            if (nums[read] != nums[read - 1]) {
                nums[write++] = nums[read];
            }
        }
        return write;
    }
}
```

**Kotlin 풀이**:
```kotlin
class Solution {
    fun removeDuplicates(nums: IntArray): Int {
        if (nums.isEmpty()) return 0
        var write = 1
        for (read in 1 until nums.size) {
            if (nums[read] != nums[read - 1]) {
                nums[write++] = nums[read]
            }
        }
        return write
    }
}
```

**복잡도**: O(n) 시간, O(1) 공간.

**함정**:
- 빈 배열 (`nums.length == 0`) 가드. 안 두면 `nums[read - 1]` 접근에서 IOOB는 아니지만 `write = 1` 반환이 잘못됨.
- 정렬된 입력이라는 전제를 활용 — 정렬 안 된 입력이면 HashSet으로 가야 함 (O(n) 메모리).
- LeetCode 80 (중복 최대 2번 허용) 변형: `if (read < 2 || nums[read] != nums[write - 2])` 로 일반화 가능.

---

### 6.5 LeetCode 125 — Valid Palindrome

**한국어 요약**: 영숫자만 비교 (대소문자 무시) 하여 문자열이 회문인지 판정.

**접근**: 양 끝 좁히기 + 문자 필터링. 새 문자열을 만들면 O(n) 메모리 낭비 → 인덱스 두 개로 in-place 스캔.

**Java 풀이**:
```java
class Solution {
    public boolean isPalindrome(String s) {
        int left = 0, right = s.length() - 1;
        while (left < right) {
            // 영숫자가 아닌 문자는 skip
            while (left < right && !Character.isLetterOrDigit(s.charAt(left))) left++;
            while (left < right && !Character.isLetterOrDigit(s.charAt(right))) right--;
            char lc = Character.toLowerCase(s.charAt(left));
            char rc = Character.toLowerCase(s.charAt(right));
            if (lc != rc) return false;
            left++; right--;
        }
        return true;
    }
}
```

**Kotlin 풀이**:
```kotlin
class Solution {
    fun isPalindrome(s: String): Boolean {
        var left = 0
        var right = s.length - 1
        while (left < right) {
            while (left < right && !s[left].isLetterOrDigit()) left++
            while (left < right && !s[right].isLetterOrDigit()) right--
            if (s[left].lowercaseChar() != s[right].lowercaseChar()) return false
            left++; right--
        }
        return true
    }
}
```

**복잡도**: O(n) 시간, O(1) 공간 (새 문자열 안 만듦).

**함정**:
- 빈 문자열 또는 영숫자 0개 → true (즉시 while 안 들어가서 OK).
- inner while에서 `left < right` 가드 안 두면 무한 루프 또는 IOOB.
- `Character.isLetterOrDigit`는 Unicode 인식 — 한글, 일본어도 letter로 판정. 문제에서 ASCII만 원하면 추가 검사 필요. LeetCode 125는 Unicode 허용이라 그대로 OK.
- 대소문자 통일: `toLowerCase`만 비교 시점에 — `s` 전체를 toLowerCase 하면 O(n) 메모리.

---

### 6.6 LeetCode 75 — Sort Colors (Dutch National Flag)

**한국어 요약**: 0, 1, 2만 들어있는 배열을 in-place 정렬. 라이브러리 sort 금지 (실전 면접에선 항상 그럴 것).

**접근**: 3-pointer Dutch flag. `low/mid/high` 세 영역으로 나눠 mid가 한 번만 스캔.

**Java 풀이**:
```java
class Solution {
    public void sortColors(int[] nums) {
        int low = 0, mid = 0, high = nums.length - 1;
        while (mid <= high) {
            if (nums[mid] == 0) {
                swap(nums, low++, mid++);
            } else if (nums[mid] == 1) {
                mid++;
            } else { // nums[mid] == 2
                swap(nums, mid, high--);
                // mid는 그대로 — 방금 high에서 받은 값을 재검사해야 함
            }
        }
    }
    private void swap(int[] a, int i, int j) {
        int t = a[i]; a[i] = a[j]; a[j] = t;
    }
}
```

**Kotlin 풀이**:
```kotlin
class Solution {
    fun sortColors(nums: IntArray): Unit {
        var low = 0
        var mid = 0
        var high = nums.size - 1
        while (mid <= high) {
            when (nums[mid]) {
                0 -> { val t = nums[low]; nums[low] = nums[mid]; nums[mid] = t; low++; mid++ }
                1 -> mid++
                2 -> { val t = nums[mid]; nums[mid] = nums[high]; nums[high] = t; high-- }
            }
        }
    }
}
```

**복잡도**: O(n) 시간 (한 번 스캔), O(1) 공간.

**함정**:
- **mid를 case 2에서 증가시키면 안 됨** — high에서 swap된 값이 0/1/2 무엇인지 미확인. 가장 흔한 버그.
- `while (mid <= high)` (≤ 아닌 < 쓰면 마지막 한 자리 빠뜨림).
- 2-pass 풀이 (counting sort)는 O(n)이지만 두 번 훑음. Dutch flag는 1-pass — 인터뷰는 1-pass를 원함.
- 일반화: 음수/0/양수 분리, pivot 기준 partition 등 — quicksort 3-way partition으로 직결.

---

## 7. 함정·엣지케이스 종합

### 7.1 Off-by-one — `<` vs `<=`

| 상황 | 올바른 조건 | 잘못된 결과 |
|---|---|---|
| 양 끝, 같은 원소 재사용 금지 | `left < right` | `<=`면 자기 자신과 짝지음 (예: Two Sum II에서 `[3]` + `[3]` = 6) |
| Dutch flag | `mid <= high` | `<`면 마지막 한 자리 미검사 |
| fast-slow (정렬된 중복 제거) | `read < n` | 빈 배열에서 `nums[read - 1]` IOOB |
| 회문 inner skip | `left < right && !isAlnum(...)` | 가드 없으면 끝까지 가서 IOOB |

### 7.2 중복 처리 (3Sum류)

```
   정답 [0, 0, 0] 발견 후
   left++, right-- 했는데 옆도 0이면 같은 답 또 발견
   → "while (left < right && nums[left] == nums[left-1]) left++"
   세 자리 모두 (i, left, right) skip 필요
```

빠뜨리면 LeetCode WA, 면접에서는 즉시 지적당함.

### 7.3 정렬 후 인덱스 의미 변화

- LeetCode 1 (Two Sum, 정렬 안 됨) → 원래 인덱스 반환 → 정렬하면 정보 손실 → **HashMap** 필요.
- LeetCode 167 (sorted) → 정렬 인덱스가 곧 답 → 투포인터 OK.
- 원래 인덱스를 보존하려면 `(value, originalIndex)` pair 배열로 정렬.

### 7.4 빈 입력 / 단일 원소

| 케이스 | 처리 |
|---|---|
| `nums.length == 0` | 즉시 0/특수값 반환. while 조건 `left < right`가 0 < -1로 false라 들어가지 않으니 보통 자연 처리. 단, 첫 줄에 `nums[0]` 접근하는 코드는 가드. |
| `nums.length == 1` | 쌍을 못 만듦. Remove duplicates는 1 반환. Two Sum은 답 없음. |
| 모든 원소가 같음 | 3Sum에서 `[0,0,0]` 처리 — 중복 skip이 너무 빨라서 정답 1개만 나와야 함. |

### 7.5 Overflow

- `int + int`가 `Integer.MAX_VALUE` 근처면 overflow → **`long`으로 캐스팅**.
- LeetCode 167처럼 값 범위가 큰 문제 (`-2^31 ≤ nums[i] ≤ 2^31 - 1`)는 두 수 합만으로도 int 초과 → 습관적으로 `long`.
- Kotlin은 `toLong()` 명시 (자동 변환 없음).

### 7.6 in-place 의미

- "in-place"는 **결과를 입력 배열 안에서 만들기**. 새 배열 alloc 금지.
- LeetCode 채점은 `nums`의 앞 `k`개만 보고 뒤는 무시 (k는 return 값).
- `nums.length`는 변하지 않음 — Java/Kotlin 배열은 고정 길이.

---

## 8. 꼬리질문 트리

```
   [기본 투포인터 정답 제출]
            │
   "정렬이 안 되어 있다면?"
            │
            ├── 원래 인덱스 반환 필요 → HashMap O(n) 공간
            │
            └── 인덱스 무관, 값만 → 정렬 O(n log n) + 투포인터

   "K-Sum으로 일반화하면?"
            │
            ├── K=2 (sorted): 양 끝 좁히기 O(n)
            ├── K=3: 1개 고정 + 2Sum  → O(n²)
            ├── K=4: 2개 고정 + 2Sum  → O(n³)
            └── K개: 재귀 + 2Sum base case → O(n^(K-1))

   "스트리밍 입력 (전체를 못 본다)이면?"
            │
            ├── 정렬 불가 → 투포인터 불가
            └── HashSet + 순회로 페어 찾기, top-K는 PriorityQueue

   "메모리 O(1)을 유지하려면?"
            │
            ├── 정렬은 in-place quicksort/heapsort
            └── HashMap 대신 투포인터

   "n이 매우 큰데 추가 쿼리가 반복되면?"
            │
            └── 한 번 정렬 후 매 쿼리마다 O(n) 또는 O(log n) — DB index의 idea

   "음수·0·양수가 섞이고 합을 0에 가장 가깝게는?"
            │
            └── 2Sum closest, 3Sum closest — 양 끝 좁히기 + best 추적

   "중복 입력을 효율적으로 다루려면?"
            │
            └── while skip이 표준, 또는 LinkedHashSet으로 사전 dedup
```

각 가지의 시간/공간 trade-off를 즉답할 수 있어야 마스터.

---

## 9. 다른 패턴과의 연결

### 9.1 슬라이딩 윈도우와의 같은 점·다른 점

```
   [Sliding Window]              [Two Pointers (fast-slow)]
   left와 right가 한 방향        left와 right가 한 방향
   right가 확장, left가 수축     read가 확장, write가 받음
   "윈도우 안 상태"를 유지       "지금까지 만든 결과"를 유지
   조건이 깨지면 left 전진       값이 맞으면 write 전진
   → 부분 배열의 합/길이/개수    → 원소 분류·이동
```

**핵심 차이**: 슬라이딩 윈도우는 **구간을 만들고 그 구간의 집계량을 본다**. 투포인터 fast-slow는 **개별 원소를 분류해 옮긴다**. 둘 다 두 포인터를 같은 방향으로 쓰지만 의미가 다름.

**경계 사례** (둘 다로 풀리는 문제): "정렬된 배열에서 합이 ≤ target인 부분 배열" — 양 끝 좁히기로도, 슬라이딩 윈도우로도 풀린다.

### 9.2 이분 탐색으로 대체 가능한 경우

```
   정렬된 배열에서 합이 target인 쌍 찾기
   ────────────────────────────────────
   방법 A: 양 끝 좁히기 — O(n)
   방법 B: 각 i에 대해 (target - nums[i])를 binary search — O(n log n)

   → 둘 다 정답, 투포인터가 더 빠름.
   → 그러나 문제 변형(예: 정렬된 배열에서 합이 K개 이상)에서는 binary search가 더 자연스러울 수 있음.
```

면접에서 "더 빠르게?"라고 물으면 둘의 우열을 설명할 수 있어야 함.

### 9.3 quicksort partition과의 뿌리

Dutch flag 3-way partition은 **Sedgewick·Bentley·McIlroy의 3-way quicksort 핵심 루틴**. 중복 키가 많은 입력에서 일반 quicksort는 `O(n²)`로 degrade하지만 3-way는 `O(n)` 유지. 코딩 테스트의 sortColors는 단독 문제로 보이지만 실은 production-grade quicksort 내부 모듈을 만드는 것.

### 9.4 연결 리스트의 fast/slow (Floyd cycle detection)

배열의 fast-slow와 같은 패턴이 연결 리스트에서는:
- **cycle 검출** (Floyd Tortoise and Hare): slow는 1칸, fast는 2칸. 만나면 cycle.
- **중간 노드 찾기**: fast가 끝에 도달했을 때 slow가 중앙.
- **k번째 끝에서 노드**: fast를 k 먼저 보내고 둘 다 진행.

뒤 챕터 (Linked List)에서 이어진다.

### 9.5 시니어 운영 관점 — 시스템에서 보이는 투포인터의 그림자

| 시스템 | 투포인터의 그림자 |
|---|---|
| **DB sort-merge join** | 양 정렬된 테이블을 한 번씩 스캔, 작은 키 advance — 양 끝이 아닌 두 시퀀스 병합형 |
| **DB index range scan** | sorted index에서 `WHERE a ≤ x ≤ b` — 양 끝 좁히기의 정신적 모델 |
| **Kafka log compaction** | offset 정렬된 segment 스캔, 중복 key의 최신만 유지 — fast-slow in-place 제거의 distributed 버전 |
| **TCP 송수신 윈도우** | sliding window의 사촌 — left/right가 확정 수신/전송 경계 |
| **3-way merge in Git** | 두 branch + base의 동시 스캔 — 일반화된 multi-pointer |

투포인터는 단순 인터뷰 패턴이 아니라 **두 개 이상의 정렬된 시퀀스를 동시에 한 번씩 훑는 모든 시스템 알고리즘의 원형**이다. 인터뷰에서 답을 빨리 내는 게 1차 목표지만, 실무에서 "왜 sort-merge join이 hash join보다 메모리에 친절한가"를 답하는 같은 사고 회로를 키우는 게 진짜 목표.

---

## 10. 백지 자가 점검 체크리스트

이 챕터를 덮고 백지에서 다음을 줄줄 풀어낼 수 있어야 마스터 레벨이다.

- [ ] 6가지 변형 ASCII (양 끝 / fast-slow / in-place 분리 / Dutch flag / 회문 / 두 정렬 병합)을 그릴 수 있다.
- [ ] "왜 정렬이 전제인가"를 단조성으로 설명할 수 있다.
- [ ] LeetCode 167 / 15 / 11 / 26 / 125 / 75를 Java와 Kotlin 양쪽으로 백지에서 쓸 수 있다.
- [ ] Container With Most Water에서 "왜 짧은 쪽을 옮기는가"를 30초 안에 증명할 수 있다.
- [ ] Dutch flag에서 case 2일 때 왜 mid를 증가시키지 않는지 설명할 수 있다.
- [ ] off-by-one (`< vs <=`), overflow (`int vs long`), 중복 skip 세 함정을 모두 코드에 반영한다.
- [ ] K-Sum 일반화의 시간 복잡도 `O(n^(K-1))`를 유도할 수 있다.
- [ ] 슬라이딩 윈도우, 이분 탐색, quicksort 3-way partition과의 연결을 말할 수 있다.
- [ ] 시스템 관점에서 sort-merge join, index range scan과 투포인터의 공통 원리를 설명할 수 있다.

여기까지 되면 라이브 코딩 테스트에서 투포인터 류 문제는 **30초 안에 패턴 분류 → 5분 안에 정답 → 10분 안에 엣지 케이스까지** 마무리할 수 있다.
