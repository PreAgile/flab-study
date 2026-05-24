# 15. Prefix Sum (누적합)

> "for문으로 합 구하면 되는 거 아닌가요?" 라고 답하면 입문자.
> 마스터는 **"구간 합 쿼리가 여러 번 들어오는 순간 O(N·Q) → O(N+Q)로 떨어뜨리는 전처리 trick"** 으로 본다. 더 나아가 **prefix sum mod K + hashmap** 으로 "정확히 K 만큼 / K의 배수인 부분배열 개수" 같은 O(N²) 브루트포스를 O(N)으로 만드는 게 진짜 본질이다.
>
> 시니어 운영 관점: 시계열 누적 통계(분당 요청 수의 분 단위 → 시간 단위 합산), 대시보드 range query(특정 기간 PV/UV), 페이지 view counter, A/B 테스트 노출수 집계 — 전부 prefix sum이다. PostgreSQL window function의 `SUM(x) OVER (ORDER BY t)`, Prometheus `increase()` 모두 prefix sum의 변형.

---

## 0. 인지 신호 (이 패턴을 30초에 알아차리는 법)

문제에서 다음 키워드가 보이면 **prefix sum**을 떠올린다.

| 신호 | 예시 표현 | 왜 prefix sum인가 |
|---|---|---|
| **다중 구간 합 쿼리** | "Q개의 쿼리, 각 쿼리마다 [l, r] 합" | 매 쿼리 O(r-l+1) → 총 O(NQ). prefix로 전처리하면 쿼리당 O(1) |
| **정확히 K** | "합이 정확히 K인 부분배열 개수" | prefix[j]-prefix[i]=K → prefix[i]=prefix[j]-K. hashmap으로 O(N) |
| **K의 배수** | "합이 K의 배수인 부분배열 개수" | (prefix[j] mod K) == (prefix[i] mod K)이면 구간 합이 K의 배수 |
| **2D 부분 직사각형 합** | "(r1,c1)~(r2,c2) 합" | 2D prefix sum, 포함-배제 |
| **차분 배열 (range update)** | "구간 [l,r]에 +v를 Q번, 마지막 배열은?" | diff[l]+=v, diff[r+1]-=v → prefix로 복원, O(N+Q) |
| **연속 부분배열의 평균/카운트** | "두 종류 원소가 같은 수만큼" | 한 종류를 +1, 다른 종류를 -1로 치환 → prefix sum 같은 인덱스 |
| **suffix product / prefix product** | "자기 자신 제외한 곱" | prefix product × suffix product |
| **트리 path sum K** | "루트→임의 노드 경로 합 K" | DFS 중 prefix path sum + hashmap |

핵심 변별: **"구간"이라는 단어 + "여러 번" 또는 "정확히/배수"** 가 동시에 나오면 prefix sum이다.

**Sliding Window와의 차이**: sliding window는 "단조성"이 있어야 한다 (양수만, 또는 단조 증가). prefix sum + hashmap은 **음수 포함, 0 포함, 어떤 값이든** 동작한다. Subarray Sum Equals K가 sliding window로 안 풀리는 이유.

---

## 1. 백지 그리기 — 패턴 시각화

### 1.1 1D Prefix Sum (가장 기본)

```
배열 a:     a[0]=3   a[1]=1   a[2]=4   a[3]=1   a[4]=5
인덱스:       0        1        2        3        4

prefix[i+1] = prefix[i] + a[i],  prefix[0] = 0

prefix:    [ 0,   3,   4,   8,   9,   14 ]
인덱스:      0    1    2    3    4    5
             ↑                          ↑
             "0개 합"                "5개 합 = 14"

구간 합 [l..r] (양쪽 포함) = prefix[r+1] - prefix[l]

예) [1..3] 합 = a[1]+a[2]+a[3] = 1+4+1 = 6
    검증: prefix[4] - prefix[1] = 9 - 3 = 6 ✓
```

**왜 prefix[0]=0?** off-by-one을 막기 위한 sentinel. "0개의 원소 합 = 0"이라는 약속. 이게 없으면 l=0인 쿼리에서 if 분기를 또 써야 한다.

**왜 prefix[i+1]에 a[i]?** prefix[i] = "a[0..i-1]의 합" = "앞에서 i개의 합". 이 정의가 r+1, l 두 인덱스 빼기로 자연스럽게 떨어진다.

### 1.2 2D Prefix Sum

```
grid (3x4):
        col 0  col 1  col 2  col 3
row 0 [  1      2      3      4  ]
row 1 [  5      6      7      8  ]
row 2 [  9     10     11     12  ]

P[i+1][j+1] = P[i][j+1] + P[i+1][j] - P[i][j] + grid[i][j]
                ↑           ↑           ↑
              위 직사각형   왼 직사각형  중복 빠진 부분 (포함-배제)

P (4x5):
         0    1    2    3    4
    0 [  0    0    0    0    0 ]
    1 [  0    1    3    6   10 ]
    2 [  0    6   14   24   36 ]
    3 [  0   15   33   54   78 ]

부분 직사각형 [r1..r2][c1..c2] 합
= P[r2+1][c2+1] - P[r1][c2+1] - P[r2+1][c1] + P[r1][c1]

예) (1,1)~(2,2) 합 = 6+7+10+11 = 34
    P[3][3] - P[1][3] - P[3][1] + P[1][1]
    = 54 - 6 - 15 + 1 = 34 ✓
```

**포함-배제 (inclusion-exclusion)**: 큰 직사각형에서 위·왼쪽을 빼면 좌상단이 두 번 빠지므로 다시 더한다. Venn diagram 두 원의 합집합 = A + B - A∩B와 같은 원리.

### 1.3 차분 배열 (Difference Array) — Prefix Sum의 역연산

```
원본:    a = [ 3, 1, 4, 1, 5 ]
차분:    d[i] = a[i] - a[i-1],  d[0] = a[0]

d = [ 3, -2, 3, -3, 4 ]

복원: prefix sum of d = a 그대로

핵심 trick: 구간 [l..r]에 +v를 추가하고 싶을 때
   d[l]   += v
   d[r+1] -= v
   → 마지막에 prefix sum 한 번으로 a 복원, O(1) range update

예) [1..3]에 +10
   d = [3, -2+10, 3, -3, 4-(-10)... ]
       = [3,  8,   3, -3, 14]  (인덱스 5는 가상)
   prefix sum: [3, 11, 14, 11, 15+... ]
   → a' = [3, 11, 14, 11, 15] (원본에 [1..3]만 +10 더해진 것)
```

**왜 차분 배열인가?** Q번의 range update + 마지막에 1번 조회면 O(N+Q). Q번 range update를 매번 O(N)으로 하면 O(NQ). 면접에서 "구간에 더하는 쿼리 여러 번, 마지막에 한 번 출력"이 나오면 무조건 차분 배열.

### 1.4 Hashmap + Prefix Sum (Subarray Sum Equals K)

```
배열 a: [1, 2, 3, -2, 5],  K = 5
prefix: [0, 1, 3, 6,  4, 9]

질문: prefix[j] - prefix[i] = K 인 (i, j) 쌍 개수?
      ⇔ prefix[i] = prefix[j] - K

j=0, prefix[0]=0, 찾을 값 0-5=-5. count[-5] = 0. count[0]++ → {0:1}
j=1, prefix[1]=1, 찾을 값 1-5=-4. count[-4] = 0. count[1]++ → {0:1, 1:1}
j=2, prefix[2]=3, 찾을 값 3-5=-2. count[-2] = 0. count[3]++
j=3, prefix[3]=6, 찾을 값 6-5= 1. count[1] = 1 → answer += 1. count[6]++
j=4, prefix[4]=4, 찾을 값 4-5=-1. count[-1] = 0. count[4]++
j=5, prefix[5]=9, 찾을 값 9-5= 4. count[4] = 1 → answer += 1. count[9]++

answer = 2  (부분배열 [2,3] 합 5, [3,-2,5,... wait] 재확인)
실제: [2,3]=5 ✓, [3,-2,5,...] 아니 [-2,5,...] 한번 더 확인:
   a[3..4] = -2+5 = 3 ✗
   a[2..4] = 3-2+5 = 6 ✗
   a[3..3] = -2 ✗
   a[1..4] = 2+3-2+5 = 8 ✗
   a[0..3] = 1+2+3-2 = 4 ✗
   a[2..3] = 3-2 = 1 ✗
   → 위 trace에서 두 번째 +1은 [3..4] 아니라 ... 다시 계산:
   prefix=[0,1,3,6,4,9], 차이 5인 쌍: (0,2) 3-(-2)... 아니
   (prefix[j]=5+prefix[i]): j=2 prefix=3, need i=-2, X
                            j=3 prefix=6, need i=1 ✓ → [1..2] = 2+3 = 5 ✓
                            j=5 prefix=9, need i=4 ✓ → [4..4] = 5 ✓
   answer = 2 ✓
```

**핵심 통찰**: prefix를 다 만들고 hashmap을 쓰는 게 아니라, **한 번의 패스에서 prefix를 계산하면서 hashmap에 누적**한다. j 시점에서 hashmap은 "j 이전의 모든 i의 prefix[i] 분포". 그래서 O(N) 한 번에 끝난다.

**왜 음수도 가능한가**: sliding window는 "확장하면 합이 증가"라는 단조성에 의존. 음수가 섞이면 단조성 깨짐. prefix sum은 **빼기**로 구간 합을 구하므로 부호 무관.

### 1.5 Prefix Sum mod K (Subarray Sums Divisible by K)

```
배열 a: [4, 5, 0, -2, -3, 1],  K = 5
prefix: [0, 4, 9, 9, 7, 4, 5]
prefix mod K (음수 보정 후): 
   prefix[0]%5 = 0
   prefix[1]%5 = 4
   prefix[2]%5 = 4
   prefix[3]%5 = 4
   prefix[4]%5 = 2
   prefix[5]%5 = 4    ← (-3 더하면 4: ((4-3)%5+5)%5 = 1 아닌가? 재계산)
```

정확한 계산:
```
a = [4, 5, 0, -2, -3, 1]
prefix[0]=0
prefix[1]=4
prefix[2]=9
prefix[3]=9
prefix[4]=7
prefix[5]=4
prefix[6]=5

mod 5: [0, 4, 4, 4, 2, 4, 0]
같은 나머지를 가진 쌍 개수:
   나머지 0: 2개 → C(2,2)=1
   나머지 4: 4개 → C(4,2)=6
   나머지 2: 1개 → 0
합 = 7
```

**핵심 정리**: `(prefix[j] - prefix[i]) % K == 0` ⇔ `prefix[j] % K == prefix[i] % K`. 같은 나머지 그룹 내에서 C(n,2)만큼 쌍.

**음수 mod 함정**: Java/Kotlin은 `(-3) % 5 == -3`. 우리는 0~K-1 범위 나머지가 필요하므로 `((x % K) + K) % K`. 이거 안 하면 정답 빗나간다.

---

## 2. 직관과 정의

### 2.1 한 줄 비유

**"매일 입출금 통장 잔액 = prefix sum"**. 1일 잔액부터 N일 잔액까지 기록해두면, "3일~7일 사이 입출금 합"은 잔액(7일) - 잔액(2일). prefix sum 전처리는 통장 잔액을 매일 적어두는 것. 구간 합 쿼리는 두 날짜의 잔액 차.

### 2.2 정확한 정의

**1D Prefix Sum** (size N+1 배열):
```
prefix[0] = 0
prefix[i] = prefix[i-1] + a[i-1]    (i = 1..N)
구간 합 a[l..r] = prefix[r+1] - prefix[l]
```

**2D Prefix Sum** (size (R+1)×(C+1)):
```
P[0][*] = P[*][0] = 0
P[i+1][j+1] = P[i][j+1] + P[i+1][j] - P[i][j] + grid[i][j]
부분 직사각형 합 (r1,c1)~(r2,c2) = P[r2+1][c2+1] - P[r1][c2+1] - P[r2+1][c1] + P[r1][c1]
```

**차분 배열** (range update, single query):
```
d[0]   = a[0]
d[i]   = a[i] - a[i-1]
range update [l..r] += v:  d[l] += v;  d[r+1] -= v
복원: a[i] = prefix sum of d
```

**Hashmap + Prefix** (Subarray Sum = K):
```
count = {0: 1}  // prefix sum 0이 한 번 (빈 시작)
cur = 0
for x in a:
    cur += x
    answer += count[cur - K]
    count[cur] += 1
```

**Prefix Sum mod K**:
```
count = {0: 1}
cur = 0
for x in a:
    cur = ((cur + x) % K + K) % K
    answer += count[cur]
    count[cur] += 1
```

### 2.3 본질 — 왜 동작하는가

핵심은 **"구간을 두 점의 차이로 표현한다"**. 구간 [l..r] 합 = (앞에서 r+1개 합) - (앞에서 l개 합). 이 한 줄이 prefix sum 전체를 관통한다.

이걸 응용한 게:
- **차이가 K** → hashmap으로 짝 찾기 (Two Sum과 본질 동일)
- **차이가 K의 배수** → 같은 mod 그룹 찾기
- **2D** → 좌상단 누적 + 포함-배제로 임의 직사각형 차이
- **차분** → 역연산으로 range update를 단일 update 두 개로 변환

---

## 3. Java 템플릿

### 3.1 1D Prefix Sum (Range Sum Query)

```java
class NumArray {
    private final long[] prefix;  // overflow 대비 long

    public NumArray(int[] nums) {
        int n = nums.length;
        prefix = new long[n + 1];
        for (int i = 0; i < n; i++) {
            prefix[i + 1] = prefix[i] + nums[i];
        }
    }

    public int sumRange(int left, int right) {
        // [left..right] inclusive
        return (int)(prefix[right + 1] - prefix[left]);
    }
}
```

**왜 long?** `nums[i] <= 1e4`, n <= 1e4면 max 1e8로 int 안전하지만, n=1e5에 값 1e9이면 1e14 → long 필수. 면접에서 "범위 못 봤어요"는 감점. 무조건 long으로 시작하고 return에서 캐스팅.

### 3.2 2D Prefix Sum (Range Sum 2D)

```java
class NumMatrix {
    private final long[][] P;

    public NumMatrix(int[][] matrix) {
        int r = matrix.length, c = matrix[0].length;
        P = new long[r + 1][c + 1];
        for (int i = 0; i < r; i++) {
            for (int j = 0; j < c; j++) {
                P[i + 1][j + 1] = P[i][j + 1] + P[i + 1][j] - P[i][j] + matrix[i][j];
            }
        }
    }

    public int sumRegion(int r1, int c1, int r2, int c2) {
        return (int)(P[r2 + 1][c2 + 1] - P[r1][c2 + 1] - P[r2 + 1][c1] + P[r1][c1]);
    }
}
```

### 3.3 차분 배열 (Range Update)

```java
class DiffArray {
    private final long[] d;
    private final int n;

    public DiffArray(int[] a) {
        n = a.length;
        d = new long[n + 1];  // d[n]은 sentinel
        for (int i = 0; i < n; i++) {
            d[i] += a[i];
            d[i + 1] -= a[i];   // 이렇게 하면 d[i] = a[i]-a[i-1] 자동
        }
        // 또는 더 직관적으로:
        // d[0] = a[0];
        // for (int i = 1; i < n; i++) d[i] = a[i] - a[i-1];
    }

    public void rangeAdd(int l, int r, int v) {
        d[l] += v;
        if (r + 1 < n) d[r + 1] -= v;
    }

    public int[] build() {
        int[] result = new int[n];
        long cur = 0;
        for (int i = 0; i < n; i++) {
            cur += d[i];
            result[i] = (int) cur;
        }
        return result;
    }
}
```

### 3.4 Hashmap Prefix (Subarray Sum Equals K)

```java
class Solution {
    public int subarraySum(int[] nums, int k) {
        Map<Long, Integer> count = new HashMap<>();
        count.put(0L, 1);   // 빈 prefix
        long cur = 0;
        int answer = 0;
        for (int x : nums) {
            cur += x;
            answer += count.getOrDefault(cur - k, 0);
            count.merge(cur, 1, Integer::sum);
        }
        return answer;
    }
}
```

**순서 함정**: `count.merge` 를 먼저 하면 자기 자신을 카운트해서 틀린다. `answer += ...` 먼저, 그 다음 `count.merge`. **항상 "조회 → 갱신" 순서**.

**count.put(0L, 1)?** "prefix sum이 0인 시작점이 1개" → 첫 원소부터 정확히 K가 되는 부분배열을 잡기 위한 sentinel.

### 3.5 Prefix Sum mod K (Subarray Sums Divisible by K)

```java
class Solution {
    public int subarraysDivByK(int[] nums, int k) {
        Map<Integer, Integer> count = new HashMap<>();
        count.put(0, 1);
        int cur = 0;
        int answer = 0;
        for (int x : nums) {
            cur = ((cur + x) % k + k) % k;   // 음수 보정
            answer += count.getOrDefault(cur, 0);
            count.merge(cur, 1, Integer::sum);
        }
        return answer;
    }
}
```

또는 배열 기반 (K가 작을 때 빠름):
```java
int[] cnt = new int[k];
cnt[0] = 1;
int cur = 0, ans = 0;
for (int x : nums) {
    cur = ((cur + x) % k + k) % k;
    ans += cnt[cur];
    cnt[cur]++;
}
return ans;
```

### 3.6 트리 Prefix (Path Sum III)

```java
class Solution {
    private int answer = 0;
    private long target;
    private Map<Long, Integer> count;

    public int pathSum(TreeNode root, int targetSum) {
        target = targetSum;
        count = new HashMap<>();
        count.put(0L, 1);
        dfs(root, 0L);
        return answer;
    }

    private void dfs(TreeNode node, long cur) {
        if (node == null) return;
        cur += node.val;
        answer += count.getOrDefault(cur - target, 0);
        count.merge(cur, 1, Integer::sum);

        dfs(node.left, cur);
        dfs(node.right, cur);

        // backtrack: 형제 서브트리로 갈 때 이 경로의 prefix는 빼야 함
        count.merge(cur, -1, Integer::sum);
    }
}
```

**왜 backtrack?** 트리에서 prefix path sum은 "루트→현재 노드 경로"의 합. DFS로 내려가면서 hashmap에 누적하고, 형제 서브트리로 돌아갈 때 빼야 다른 경로와 섞이지 않는다. **백트래킹 + hashmap의 결합**.

### 3.7 Prefix/Suffix Product (Product Except Self)

```java
class Solution {
    public int[] productExceptSelf(int[] nums) {
        int n = nums.length;
        int[] ans = new int[n];

        // 1패스: ans[i] = nums[0..i-1] 곱
        ans[0] = 1;
        for (int i = 1; i < n; i++) {
            ans[i] = ans[i - 1] * nums[i - 1];
        }

        // 2패스: 뒤에서 suffix product를 누적 곱
        int suffix = 1;
        for (int i = n - 1; i >= 0; i--) {
            ans[i] = ans[i] * suffix;
            suffix *= nums[i];
        }
        return ans;
    }
}
```

**O(1) extra space 트릭**: 출력 배열에 prefix를 먼저 채우고, 뒤에서 suffix를 곱해가며 덮어씀. 분할 정복이 아니라 **두 방향 누적의 곱**.

---

## 4. Kotlin 템플릿

### 4.1 1D Prefix Sum

```kotlin
class NumArray(nums: IntArray) {
    private val prefix = LongArray(nums.size + 1)

    init {
        for (i in nums.indices) {
            prefix[i + 1] = prefix[i] + nums[i]
        }
    }

    fun sumRange(left: Int, right: Int): Int =
        (prefix[right + 1] - prefix[left]).toInt()
}
```

또는 더 idiomatic하게:
```kotlin
class NumArray(nums: IntArray) {
    private val prefix: LongArray =
        nums.fold(LongArray(nums.size + 1)) { acc, _ -> acc }
            .also {
                for (i in nums.indices) it[i + 1] = it[i] + nums[i]
            }

    fun sumRange(left: Int, right: Int): Int =
        (prefix[right + 1] - prefix[left]).toInt()
}
```

(fold는 좀 부자연스러우니 명시적 for문이 낫다.)

### 4.2 2D Prefix Sum

```kotlin
class NumMatrix(matrix: Array<IntArray>) {
    private val P: Array<LongArray>

    init {
        val r = matrix.size
        val c = matrix[0].size
        P = Array(r + 1) { LongArray(c + 1) }
        for (i in 0 until r) {
            for (j in 0 until c) {
                P[i + 1][j + 1] =
                    P[i][j + 1] + P[i + 1][j] - P[i][j] + matrix[i][j]
            }
        }
    }

    fun sumRegion(r1: Int, c1: Int, r2: Int, c2: Int): Int =
        (P[r2 + 1][c2 + 1] - P[r1][c2 + 1] - P[r2 + 1][c1] + P[r1][c1]).toInt()
}
```

### 4.3 차분 배열

```kotlin
class DiffArray(a: IntArray) {
    private val n = a.size
    private val d = LongArray(n + 1)

    init {
        for (i in a.indices) {
            d[i] += a[i]
            d[i + 1] -= a[i]
        }
    }

    fun rangeAdd(l: Int, r: Int, v: Int) {
        d[l] += v
        if (r + 1 < n) d[r + 1] -= v
    }

    fun build(): IntArray {
        val result = IntArray(n)
        var cur = 0L
        for (i in 0 until n) {
            cur += d[i]
            result[i] = cur.toInt()
        }
        return result
    }
}
```

### 4.4 Hashmap Prefix (Subarray Sum Equals K)

```kotlin
fun subarraySum(nums: IntArray, k: Int): Int {
    val count = HashMap<Long, Int>()
    count[0L] = 1
    var cur = 0L
    var answer = 0
    for (x in nums) {
        cur += x
        answer += count.getOrDefault(cur - k, 0)
        count.merge(cur, 1) { old, new -> old + new }
    }
    return answer
}
```

### 4.5 Prefix Sum mod K

```kotlin
fun subarraysDivByK(nums: IntArray, k: Int): Int {
    val cnt = IntArray(k)
    cnt[0] = 1
    var cur = 0
    var ans = 0
    for (x in nums) {
        cur = ((cur + x) % k + k) % k
        ans += cnt[cur]
        cnt[cur]++
    }
    return ans
}
```

### 4.6 트리 Prefix (Path Sum III)

```kotlin
class Solution {
    private var answer = 0
    private var target = 0L
    private val count = HashMap<Long, Int>()

    fun pathSum(root: TreeNode?, targetSum: Int): Int {
        target = targetSum.toLong()
        count[0L] = 1
        dfs(root, 0L)
        return answer
    }

    private fun dfs(node: TreeNode?, curParent: Long) {
        if (node == null) return
        val cur = curParent + node.`val`
        answer += count.getOrDefault(cur - target, 0)
        count.merge(cur, 1) { o, n -> o + n }

        dfs(node.left, cur)
        dfs(node.right, cur)

        count.merge(cur, -1) { o, n -> o + n }
    }
}
```

### 4.7 Prefix/Suffix Product

```kotlin
fun productExceptSelf(nums: IntArray): IntArray {
    val n = nums.size
    val ans = IntArray(n)
    ans[0] = 1
    for (i in 1 until n) ans[i] = ans[i - 1] * nums[i - 1]
    var suffix = 1
    for (i in n - 1 downTo 0) {
        ans[i] *= suffix
        suffix *= nums[i]
    }
    return ans
}
```

---

## 5. 시간/공간 복잡도

| 변형 | 전처리 | 쿼리 | 공간 | 비고 |
|---|---|---|---|---|
| 1D Prefix Sum | O(N) | O(1) | O(N) | Q회 쿼리 → 총 O(N+Q) |
| 2D Prefix Sum | O(R·C) | O(1) | O(R·C) | Q회 쿼리 → 총 O(RC+Q) |
| 차분 배열 (range update) | O(N) | range update O(1), 최종 build O(N) | O(N) | Q회 update → O(N+Q) |
| Hashmap Prefix (정확히 K) | — | — | O(N) | 전체 O(N), hashmap 평균 O(1) |
| Prefix Sum mod K | — | — | O(K) 또는 O(N) | 배열 카운터가 hashmap보다 빠름 |
| 트리 Prefix (Path Sum III) | — | — | O(H) (재귀 + hashmap) | O(N) DFS |
| Prefix/Suffix Product | — | — | O(1) extra (출력 배열 제외) | 2패스 |

**왜 sliding window는 O(N)인데 prefix sum + hashmap도 O(N)인가**: sliding window는 포인터 2개로 한 번 패스 → O(N). prefix + hashmap도 한 패스 + 각 단계 hashmap O(1) → O(N). 다만 hashmap이라 **상수가 sliding window보다 크다**. 양수만이면 sliding window가 더 빠르다. **음수/0 포함이면 prefix + hashmap이 유일한 O(N) 방법**.

**전처리 비용을 항상 따져야 한다**: 쿼리가 1번이면 prefix sum 전처리 O(N)은 낭비. 쿼리가 O(N) 이상이어야 손익분기. 면접에서 "쿼리가 1번이면?"이라고 물으면 "직접 O(N) 합산이 더 효율적"이라고 답하라.

---

## 6. 대표 문제 (6개)

### 6.1 LeetCode 303 — Range Sum Query Immutable

**요약**: 정수 배열이 주어지고, 여러 번 `sumRange(l, r)`를 호출해 [l..r] 구간 합을 반환.

**접근**: 기본 1D prefix sum. 생성자에서 전처리 O(N), 쿼리 O(1).

**Java**:
```java
class NumArray {
    private final long[] prefix;
    public NumArray(int[] nums) {
        prefix = new long[nums.length + 1];
        for (int i = 0; i < nums.length; i++)
            prefix[i + 1] = prefix[i] + nums[i];
    }
    public int sumRange(int left, int right) {
        return (int)(prefix[right + 1] - prefix[left]);
    }
}
```

**Kotlin**:
```kotlin
class NumArray(nums: IntArray) {
    private val prefix = LongArray(nums.size + 1).also {
        for (i in nums.indices) it[i + 1] = it[i] + nums[i]
    }
    fun sumRange(left: Int, right: Int): Int =
        (prefix[right + 1] - prefix[left]).toInt()
}
```

**복잡도**: 전처리 O(N), 쿼리 O(1), 공간 O(N).

**함정**:
- off-by-one: `prefix[right + 1] - prefix[left]`이 맞다. `prefix[right] - prefix[left]`로 적으면 마지막 원소가 빠진다.
- overflow: 값이 ±10^4, n이 10^4이면 합 ±10^8 (int 안전). 그러나 n=10^5라면 ±10^9 가능 — long으로 가는 게 안전 습관.

### 6.2 LeetCode 304 — Range Sum Query 2D Immutable

**요약**: 2D matrix에서 여러 번 `sumRegion(r1, c1, r2, c2)`로 부분 직사각형 합을 반환.

**접근**: 2D prefix sum + 포함-배제.

**Java**:
```java
class NumMatrix {
    private final long[][] P;
    public NumMatrix(int[][] matrix) {
        int r = matrix.length, c = matrix[0].length;
        P = new long[r + 1][c + 1];
        for (int i = 0; i < r; i++)
            for (int j = 0; j < c; j++)
                P[i + 1][j + 1] = P[i][j + 1] + P[i + 1][j] - P[i][j] + matrix[i][j];
    }
    public int sumRegion(int r1, int c1, int r2, int c2) {
        return (int)(P[r2 + 1][c2 + 1] - P[r1][c2 + 1] - P[r2 + 1][c1] + P[r1][c1]);
    }
}
```

**Kotlin**:
```kotlin
class NumMatrix(matrix: Array<IntArray>) {
    private val P: Array<LongArray>
    init {
        val r = matrix.size; val c = matrix[0].size
        P = Array(r + 1) { LongArray(c + 1) }
        for (i in 0 until r) for (j in 0 until c)
            P[i + 1][j + 1] = P[i][j + 1] + P[i + 1][j] - P[i][j] + matrix[i][j]
    }
    fun sumRegion(r1: Int, c1: Int, r2: Int, c2: Int): Int =
        (P[r2 + 1][c2 + 1] - P[r1][c2 + 1] - P[r2 + 1][c1] + P[r1][c1]).toInt()
}
```

**복잡도**: 전처리 O(R·C), 쿼리 O(1).

**함정**:
- 포함-배제 부호 헷갈림. 머릿속 그림으로 "큰 거 - 위 - 왼쪽 + 좌상단" 반복 암기.
- 빈 행렬, 1×1 행렬도 P 크기는 (1+1)×(1+1)이므로 동작. P 0번째 행/열이 0 sentinel.

### 6.3 LeetCode 560 — Subarray Sum Equals K

**요약**: 정수 배열과 K가 주어질 때, 합이 정확히 K인 부분배열(연속) 개수.

**접근**: prefix sum + hashmap. 핵심 — **음수 포함, 단조성 없음** → sliding window 불가. prefix[j] - prefix[i] = K ⇔ prefix[i] = prefix[j] - K. j를 훑으며 "지금까지의 prefix 분포"를 hashmap에 누적, `cur - K`를 hashmap에서 조회.

**Java**:
```java
public int subarraySum(int[] nums, int k) {
    Map<Long, Integer> count = new HashMap<>();
    count.put(0L, 1);
    long cur = 0;
    int answer = 0;
    for (int x : nums) {
        cur += x;
        answer += count.getOrDefault(cur - k, 0);
        count.merge(cur, 1, Integer::sum);
    }
    return answer;
}
```

**Kotlin**:
```kotlin
fun subarraySum(nums: IntArray, k: Int): Int {
    val count = HashMap<Long, Int>()
    count[0L] = 1
    var cur = 0L
    var answer = 0
    for (x in nums) {
        cur += x
        answer += count.getOrDefault(cur - k, 0)
        count.merge(cur, 1) { a, b -> a + b }
    }
    return answer
}
```

**복잡도**: O(N) 시간, O(N) 공간.

**함정**:
- 순서 — **조회 먼저, 갱신 나중**. 그렇지 않으면 K=0일 때 자기 자신 0짜리 부분배열로 카운트됨.
- `count.put(0L, 1)` sentinel — "빈 prefix가 1개"라 첫 원소부터 합이 K인 케이스가 잡힌다.
- overflow — 합이 int 범위 초과 가능. long 사용.

### 6.4 LeetCode 974 — Subarray Sums Divisible by K

**요약**: 합이 K의 배수인 부분배열 개수.

**접근**: prefix sum mod K. 같은 나머지를 가진 prefix 인덱스 쌍을 셈.

**Java**:
```java
public int subarraysDivByK(int[] nums, int k) {
    int[] cnt = new int[k];
    cnt[0] = 1;
    int cur = 0, ans = 0;
    for (int x : nums) {
        cur = ((cur + x) % k + k) % k;
        ans += cnt[cur];
        cnt[cur]++;
    }
    return ans;
}
```

**Kotlin**:
```kotlin
fun subarraysDivByK(nums: IntArray, k: Int): Int {
    val cnt = IntArray(k)
    cnt[0] = 1
    var cur = 0
    var ans = 0
    for (x in nums) {
        cur = ((cur + x) % k + k) % k
        ans += cnt[cur]
        cnt[cur]++
    }
    return ans
}
```

**복잡도**: O(N) 시간, O(K) 공간.

**함정**:
- **음수 mod**: Java `(-3) % 5 == -3`. 반드시 `((x % k) + k) % k`. 이걸 빼먹으면 절반의 케이스에서 틀린다.
- K가 매우 크면 hashmap 사용. 일반적으로 K ≤ 10^4 정도면 배열이 더 빠르다 (cache friendly).
- "같은 나머지가 m개면 C(m, 2)" 공식으로도 풀 수 있다. 정수론적 접근:
  ```
  ans = 0
  cnt[0] = 1
  // 한 패스 후 cnt[r] = prefix mod r인 개수
  // ans = sum(cnt[r] * (cnt[r] - 1) / 2)
  ```
  하지만 위 inline 누적이 더 직관적.

### 6.5 LeetCode 238 — Product of Array Except Self

**요약**: `output[i] = nums의 모든 원소 곱 / nums[i]` 를 나눗셈 없이 구하라. O(N), O(1) extra (출력 배열 제외).

**접근**: prefix product + suffix product. 출력 배열에 prefix를 먼저 쓰고, 뒤에서 suffix를 곱하며 덮어씀.

**Java**:
```java
public int[] productExceptSelf(int[] nums) {
    int n = nums.length;
    int[] ans = new int[n];
    ans[0] = 1;
    for (int i = 1; i < n; i++) ans[i] = ans[i - 1] * nums[i - 1];
    int suffix = 1;
    for (int i = n - 1; i >= 0; i--) {
        ans[i] *= suffix;
        suffix *= nums[i];
    }
    return ans;
}
```

**Kotlin**:
```kotlin
fun productExceptSelf(nums: IntArray): IntArray {
    val n = nums.size
    val ans = IntArray(n)
    ans[0] = 1
    for (i in 1 until n) ans[i] = ans[i - 1] * nums[i - 1]
    var suffix = 1
    for (i in n - 1 downTo 0) {
        ans[i] *= suffix
        suffix *= nums[i]
    }
    return ans
}
```

**복잡도**: O(N) 시간, O(1) extra 공간 (return 배열 제외).

**함정**:
- 나눗셈 금지 — 0이 섞이면 division by zero. 또한 모듈러 환경에서 나눗셈은 modular inverse 필요.
- overflow — 값 범위 큰 경우 long.
- "왜 prefix와 suffix를 따로 배열로 안 쓰지?" — 메모리 절약 트릭. 면접에서 자주 묻는다.

### 6.6 LeetCode 1248 — Count Number of Nice Subarrays

**요약**: 홀수가 정확히 K개인 부분배열 개수.

**접근**: 홀수를 1, 짝수를 0으로 치환 → "합이 정확히 K인 부분배열 개수" (Subarray Sum K) 로 환원.

**Java**:
```java
public int numberOfSubarrays(int[] nums, int k) {
    Map<Integer, Integer> count = new HashMap<>();
    count.put(0, 1);
    int cur = 0, ans = 0;
    for (int x : nums) {
        cur += (x & 1);   // 홀수면 +1
        ans += count.getOrDefault(cur - k, 0);
        count.merge(cur, 1, Integer::sum);
    }
    return ans;
}
```

**Kotlin**:
```kotlin
fun numberOfSubarrays(nums: IntArray, k: Int): Int {
    val count = HashMap<Int, Int>()
    count[0] = 1
    var cur = 0; var ans = 0
    for (x in nums) {
        cur += (x and 1)
        ans += count.getOrDefault(cur - k, 0)
        count.merge(cur, 1) { a, b -> a + b }
    }
    return ans
}
```

**복잡도**: O(N), O(N).

**함정**:
- 치환 발상이 핵심. "정확히 K개의 X" 류 문제는 X를 1, 나머지를 0으로 치환 → Subarray Sum K로 환원되는 경우가 많다.
- Sliding window 풀이도 가능 (양수만이므로) — "at most K - at most K-1" 트릭. 둘 다 알아둬야 함.

### 6.7 LeetCode 525 — Contiguous Array

**요약**: 0과 1로 이뤄진 배열에서 0과 1의 개수가 같은 최장 부분배열 길이.

**접근**: **0을 -1로 치환** → 합이 0인 최장 부분배열. prefix sum이 같은 두 인덱스 i < j이면 `(i, j]` 합이 0. j - i를 최대화.

**Java**:
```java
public int findMaxLength(int[] nums) {
    Map<Integer, Integer> firstIdx = new HashMap<>();
    firstIdx.put(0, -1);  // prefix 0이 인덱스 -1에서 처음 보임
    int cur = 0, best = 0;
    for (int i = 0; i < nums.length; i++) {
        cur += (nums[i] == 0 ? -1 : 1);
        if (firstIdx.containsKey(cur)) {
            best = Math.max(best, i - firstIdx.get(cur));
        } else {
            firstIdx.put(cur, i);  // 최초 인덱스만 저장 (길이 최대화)
        }
    }
    return best;
}
```

**Kotlin**:
```kotlin
fun findMaxLength(nums: IntArray): Int {
    val firstIdx = HashMap<Int, Int>()
    firstIdx[0] = -1
    var cur = 0; var best = 0
    for (i in nums.indices) {
        cur += if (nums[i] == 0) -1 else 1
        val seen = firstIdx[cur]
        if (seen != null) best = maxOf(best, i - seen)
        else firstIdx[cur] = i
    }
    return best
}
```

**복잡도**: O(N), O(N).

**함정**:
- **개수 세는 게 아니라 최장 길이**: hashmap에 "처음 등장한 인덱스"만 저장한다. 이미 있으면 update하지 않기 (덮어쓰면 길이 짧아짐).
- 0→-1 치환을 까먹으면 그냥 1의 개수만 셈. **"균형(같은 수)"** 단서를 보면 +1/-1 치환을 떠올리자.

### 6.8 LeetCode 437 — Path Sum III

**요약**: 이진 트리에서 합이 정확히 targetSum인 경로(연속, 위→아래 방향)의 개수. 경로 시작/끝은 임의 노드.

**접근**: DFS로 루트→현재 prefix path sum을 누적하면서 hashmap에 분포 저장. `cur - target`이 hashmap에 있으면 그 인덱스 직후부터 현재까지가 정답 경로. **backtrack 필수**.

**Java**:
```java
class Solution {
    private int answer = 0;
    private long target;
    private Map<Long, Integer> count;

    public int pathSum(TreeNode root, int targetSum) {
        target = targetSum;
        count = new HashMap<>();
        count.put(0L, 1);
        dfs(root, 0L);
        return answer;
    }

    private void dfs(TreeNode node, long parentSum) {
        if (node == null) return;
        long cur = parentSum + node.val;
        answer += count.getOrDefault(cur - target, 0);
        count.merge(cur, 1, Integer::sum);

        dfs(node.left, cur);
        dfs(node.right, cur);

        count.merge(cur, -1, Integer::sum);  // backtrack
    }
}
```

**Kotlin**:
```kotlin
class Solution {
    private var answer = 0
    private var target = 0L
    private val count = HashMap<Long, Int>()

    fun pathSum(root: TreeNode?, targetSum: Int): Int {
        target = targetSum.toLong()
        count[0L] = 1
        dfs(root, 0L)
        return answer
    }

    private fun dfs(node: TreeNode?, parentSum: Long) {
        if (node == null) return
        val cur = parentSum + node.`val`
        answer += count.getOrDefault(cur - target, 0)
        count.merge(cur, 1) { a, b -> a + b }
        dfs(node.left, cur)
        dfs(node.right, cur)
        count.merge(cur, -1) { a, b -> a + b }
    }
}
```

**복잡도**: O(N) 시간 (N = 노드 수), O(H + 서로 다른 prefix 수) 공간.

**함정**:
- **overflow**: 노드 값이 ±10^9, 깊이 1000이면 sum이 ±10^12 — long 필수.
- **backtrack 빼먹기**: 형제 서브트리로 갈 때 count에서 빼지 않으면 다른 경로와 섞여 오답.
- 순서 — 조회(answer +=) 먼저, count merge 나중.

---

## 7. 함정·엣지케이스 (운영 마스터의 체크리스트)

### 7.1 off-by-one — prefix[0] = 0 sentinel 잊지 말기

```
틀린 코드: prefix[i] = prefix[i-1] + a[i]  (i=0이면 prefix[-1] OOB)
맞는 코드: prefix[0] = 0; prefix[i+1] = prefix[i] + a[i]
구간 합:   prefix[r+1] - prefix[l]  (양쪽 inclusive)
```

면접에서 가장 자주 실수하는 부분. **"r+1, l"** 또는 **"r, l-1"** 두 컨벤션 중 하나로 통일하고 헷갈리지 말 것.

### 7.2 음수 mod 처리

```java
// 틀린 코드 (Java/Kotlin은 음수 mod가 음수)
cur = (cur + x) % k;
// 맞는 코드
cur = ((cur + x) % k + k) % k;
```

C++ %도 음수 → 음수. Python만 양수. 면접관이 "Python 풀이를 Java로 옮기시오"라고 했을 때 이 함정에서 한참 헤맨다.

### 7.3 Overflow — 항상 long을 default로

- 값 ±10^4, n=10^5 → 합 ±10^9 (int 한계 2.1×10^9에 근접)
- 값 ±10^9, n=10^5 → 합 ±10^14 (long만 가능)

**규칙**: prefix sum, prefix product, 누적 변수는 **무조건 long으로 시작**. 면접관이 "값 범위 안 봐도 되나요?"라고 묻지 않는 한 long.

### 7.4 2D 포함-배제 부호 외우기

```
sum(r1, c1, r2, c2) = P[r2+1][c2+1]  - P[r1][c2+1]  - P[r2+1][c1]  + P[r1][c1]
                       (전체 좌상단)   (위쪽 빼기)    (왼쪽 빼기)    (좌상단 다시 더)
```

부호 헷갈리면 그림. "왼쪽과 위 빼면 좌상단이 두 번 빠지니까 한 번 더해준다." 면접 중 그림 그리며 설명하면 가산점.

### 7.5 차분 배열 끝 인덱스 OOB

```java
// 잘못된 코드: d[r + 1]이 배열 밖
d[l] += v;
d[r + 1] -= v;   // r = n-1이면 d[n] OOB

// 맞는 코드 1: d를 n+1 크기로
long[] d = new long[n + 1];

// 맞는 코드 2: 분기
d[l] += v;
if (r + 1 < n) d[r + 1] -= v;
```

마지막 인덱스까지 +v가 적용되는 케이스를 처리해야 한다.

### 7.6 Subarray Sum K — 조회/갱신 순서

```java
// 틀린 코드 (자기 자신을 카운트)
count.merge(cur, 1, Integer::sum);
answer += count.getOrDefault(cur - k, 0);

// 맞는 코드: 조회 먼저
answer += count.getOrDefault(cur - k, 0);
count.merge(cur, 1, Integer::sum);
```

K=0일 때 자기 자신 길이 0짜리 부분배열이 카운트되어 결과가 부풀어 오른다.

### 7.7 Hashmap sentinel — `{0: 1}` 잊지 말기

```
틀린 코드: count = {}  // 첫 원소부터 정확히 K인 부분배열을 놓침
맞는 코드: count = {0: 1}  // "빈 prefix"가 1개라는 표지
```

이걸 빼먹으면 nums=[3], k=3에서 답 1이 아니라 0이 나온다.

### 7.8 Path Sum III backtrack 빠뜨림

```java
// 틀린 코드: backtrack 없음
private void dfs(TreeNode node, long cur) {
    if (node == null) return;
    cur += node.val;
    answer += count.getOrDefault(cur - target, 0);
    count.merge(cur, 1, Integer::sum);
    dfs(node.left, cur);
    dfs(node.right, cur);
    // count에서 빼지 않음 → 형제 서브트리로 가서 잘못된 매칭
}

// 맞는 코드: backtrack
count.merge(cur, -1, Integer::sum);
```

DFS + hashmap 패턴에서 항상 묻는 디테일.

### 7.9 빈 입력 / 단일 원소

- 빈 배열: prefix = [0]. 모든 쿼리는 정의상 invalid 또는 0.
- 단일 원소: prefix = [0, a[0]]. sumRange(0, 0) = a[0]. 동작 확인.
- 모든 원소 0 / K=0: hashmap 풀이에서 자기 자신 카운트되지 않게 순서 주의.

---

## 8. 꼬리질문 트리

| 질문 | 답 요지 |
|---|---|
| "원소가 동적으로 바뀐다면?" | Fenwick Tree (BIT) — update O(log N), 쿼리 O(log N). Prefix sum의 동적 버전. |
| "구간 update + 구간 query 둘 다 빠르게?" | Segment Tree with lazy propagation — 둘 다 O(log N). 또는 BIT 2개 (range update + range query trick). |
| "범위 [l..r]에 +v를 Q번, 마지막에 한 번 출력?" | 차분 배열, O(N + Q). |
| "2D에서 점 update + 직사각형 query?" | 2D Fenwick Tree. update O(log² N), query O(log² N). |
| "2D 차분?" | 똑같은 원리 — `d[r1][c1] += v; d[r1][c2+1] -= v; d[r2+1][c1] -= v; d[r2+1][c2+1] += v`. 마지막에 2D prefix sum. |
| "음수가 없으면 더 빨리?" | Sliding window O(N) 가능. hashmap 오버헤드 없음. |
| "합이 K 이하인 부분배열 개수?" | 양수만이면 sliding window. 음수 포함이면 prefix sum 정렬 + binary search 또는 분할정복. |
| "스트리밍에서 prefix sum?" | 누적 변수 하나로 충분. 단, hashmap이 메모리 무한 증가 — TTL/window 크기 제한 필요. |
| "트리 path sum (양방향, 임의 두 노드)?" | LCA + 두 prefix path sum 빼기. Path sum III와 다름 (Path III는 한 방향). |
| "Mod에서 prefix product?" | 곱셈은 mod inverse 필요. p가 소수면 Fermat's little theorem으로 `inv(a) = a^(p-2)`. |
| "구간 곱 쿼리?" | log를 prefix sum 하거나, segment tree로 곱 누적. log는 부동소수점 오차 주의. |

---

## 9. 다른 패턴과의 연결

### 9.1 Two Sum과 같은 본질

Subarray Sum Equals K = Two Sum on prefix array. "prefix[j] - prefix[i] = K"는 정확히 "두 수의 차가 K". hashmap 한 패스 풀이도 동일 구조.

### 9.2 Sliding Window의 음수 확장

Sliding Window는 단조성(양수, 또는 단조 함수) 필요. 음수가 들어오면 prefix sum + hashmap이 유일한 O(N). **신호 분기**:
- 양수만 + "최대/최소 길이" → Sliding Window
- 음수 포함 + "정확히 K" → Prefix Sum + Hashmap
- 양수 + "정확히 K" → 둘 다 가능. Sliding Window가 더 빠름.

### 9.3 Fenwick / Segment Tree로의 확장

Prefix sum은 **정적**. 동적 update가 들어오면:
- Fenwick Tree (BIT) — prefix sum의 자연스러운 확장. update/query 둘 다 O(log N).
- Segment Tree — 더 일반적 (max, min, gcd 등도 가능). lazy로 range update 가능.

면접에서 "원소가 바뀌면?" 질문이 들어오면 즉시 Fenwick으로 전환.

### 9.4 DP에서의 prefix sum 누적

DP 점화식에 "지난 K개 합" 같은 항이 있으면 prefix sum으로 O(1) 조회. 예: LeetCode 1218 (Longest Arithmetic Subsequence with Difference), LeetCode 1696 (Jump Game VI with deque + DP는 sliding max). Cumulative DP 가속 = prefix sum 응용.

### 9.5 Mo's Algorithm

오프라인 구간 쿼리를 √N 블록으로 정렬해 O((N+Q)√N)에 답하는 기법. prefix sum이 안 되는 쿼리(예: 구간 distinct count)에 사용. 한국 코딩 테스트엔 잘 안 나오지만 알고리즘 대회에서 빈번.

### 9.6 Production에서의 prefix sum

**시계열 모니터링**:
- Prometheus `rate(http_requests_total[5m])` = 시계열 prefix(누적 counter)의 차분 / 시간.
- Grafana range query "최근 1시간 PV" = prefix(PV) at now - prefix(PV) at now-1h.
- **본질이 prefix sum**: counter는 계속 증가하는 prefix, 구간은 두 시점의 차.

**A/B 테스트**:
- "v1 vs v2 사용자 노출 누적 추이" 대시보드 = 시간별 noted exposure의 prefix sum.

**DB window function**:
- `SUM(amount) OVER (ORDER BY date)` = SQL의 prefix sum. PostgreSQL window function 그 자체.
- `LAG(prefix) OVER (...)` 등과 결합해 "어제까지 누적 vs 오늘까지 누적" 차이를 계산.

**컨텐츠 추천**:
- "최근 N분 내 좋아요" = 시간 bucket prefix + 차분.
- 1분 단위 카운터를 24×60개 메모리에 두고, 임의 구간 합을 O(1)에 — prefix sum 그대로.

**HashMap + Prefix in 운영**:
- "정확히 K번 클릭한 세션 수" → 사용자별 클릭 시계열에 prefix + hashmap 적용.
- "5분 윈도우 안에 정확히 N건의 결제 실패" 알람 → Subarray Sum K 패턴 그대로.

---

## 10. 30초 분류 체크리스트

```
문제 읽고 30초 안에:

1. "구간 합 / 부분배열 합" 이라는 단어가 있는가?
   YES → prefix sum 후보

2. 쿼리가 여러 번인가?
   YES → 전처리 가치 있음. 1D 또는 2D prefix sum.
   NO  → 단일 패스 hashmap 또는 sliding window.

3. "정확히 K" / "K의 배수" 가 있는가?
   YES → prefix sum + hashmap (mod 처리 주의)

4. "구간에 +v 더하기" 가 여러 번 + 마지막에 출력?
   YES → 차분 배열

5. 2D grid + 부분 직사각형?
   YES → 2D prefix sum + 포함-배제

6. 트리 + 경로 합 K?
   YES → DFS + prefix path sum + hashmap + backtrack

7. 자기 제외 곱?
   YES → prefix product + suffix product (2패스)

8. 음수가 있는데 "정확히 K" / "균형" / "같은 개수"?
   YES → +1/-1 치환 후 prefix sum + hashmap

9. 동적 update가 섞여 있는가?
   YES → Fenwick Tree로 전환

10. long 쓰기. 무조건. 의심 없이.
```

---

## 11. 핵심 한 줄 요약 (백지에 적기)

- **1D**: `prefix[i+1] = prefix[i] + a[i]`, `sum[l..r] = prefix[r+1] - prefix[l]`.
- **2D**: 포함-배제 `P[r2+1][c2+1] - P[r1][c2+1] - P[r2+1][c1] + P[r1][c1]`.
- **차분**: range update `d[l] += v; d[r+1] -= v`, 복원은 prefix sum.
- **Hashmap**: Subarray Sum K = "prefix[j] - prefix[i] = K"를 Two Sum으로. sentinel `{0:1}`, 조회 먼저 갱신 나중.
- **Mod K**: 같은 나머지 prefix 쌍 카운트. 음수 보정 `((x%k)+k)%k`.
- **Tree**: DFS + path prefix + hashmap + **backtrack**.
- **Suffix Product**: 2패스, O(1) extra (출력 배열 활용).
- **항상**: long. off-by-one. sentinel.

이 11줄이 prefix sum 챕터 전부다. 백지에서 이 줄들이 떠오르면 80% 완성.
