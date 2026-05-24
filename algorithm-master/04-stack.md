# 04. Stack — 괄호 매칭부터 Monotonic Stack까지

> "Stack은 LIFO" 라고만 답하면 입문자. 시니어는 **monotonic stack**으로 "다음으로 큰 원소", "히스토그램 최대 직사각형" 같은 문제를 O(n)에 풀고, 왜 amortized O(n)인지 (각 원소 push/pop 최대 1회) 설명하고, Java에서 왜 `Stack` 클래스를 피하고 `Deque`를 쓰는지, JVM operand stack과 함수 호출 스택이 같은 자료구조라는 점까지 본다.
>
> 이 챕터는 라이브 코딩 테스트에서 stack 패턴을 30초에 분류하고, 백지에서 monotonic stack을 줄줄 그리며 풀어내는 수준이 목표다.

---

## 0. 목차

1. 인지 신호
2. 백지 그리기 (basic / monotonic / histogram)
3. 직관과 정의 (LIFO, monotonic 불변, Deque vs Stack)
4. Java 템플릿 4종
5. Kotlin 템플릿 4종
6. 시간/공간 복잡도 (왜 amortized O(n)인가)
7. 대표 문제 8개 풀이
8. 함정·엣지케이스
9. 꼬리질문 트리
10. 다른 패턴과의 연결
11. 시니어 운영 매핑

---

## 1. 인지 신호 — "이 문제는 Stack이다"

문제 설명에서 다음 키워드/구조가 보이면 머릿속 자동 분류기가 Stack을 가리켜야 한다.

| 신호 | 예시 문제 | 왜 Stack인가 |
|---|---|---|
| **괄호 매칭/짝 맞추기** | Valid Parentheses, 짝지어 제거하기 | "가장 최근에 연 것"이 가장 먼저 닫혀야 함 → LIFO |
| **이전 상태 복원** | undo/redo, 함수 호출, decode string | "직전으로 돌아가기" = pop |
| **다음으로 큰/작은 원소** | Daily Temperatures, Next Greater Element | "아직 답을 못 찾은 후보"들을 monotonic하게 보관 |
| **각 원소에서 가장 큰 직사각형** | Largest Rectangle in Histogram | 각 막대에서 좌/우로 자기보다 작은 첫 막대 = monotonic stack |
| **수식 파싱/평가** | Reverse Polish, Basic Calculator | 연산자/피연산자를 LIFO로 누적 |
| **연속 중복 제거** | 같은 숫자는 싫어요, Remove Adjacent Duplicates | top과 비교해 같으면 pop |
| **재귀를 명시 스택으로** | iterative DFS, iterative inorder | 재귀 = 호출 스택, 명시화하면 stack |

**30초 분류 룰**: "방금 본 것을 다음에 처음 다시 본다" = stack. "옛날 것을 다음에 처음 다시 본다" = queue.

**monotonic 신호**: "각 원소에 대해 왼쪽/오른쪽에서 자기보다 큰/작은 첫 원소를 찾아라"가 등장하면 **거의 확실히 monotonic stack**. brute force O(n²)을 O(n)으로 끌어내리는 표준 트릭이다.

---

## 2. 백지 그리기

### 2.1 Basic Stack — LIFO

```
push(1), push(2), push(3), pop(), push(4)

시간 t=0       t=1       t=2       t=3       t=4       t=5
┌───┐     ┌───┐     ┌───┐     ┌───┐     ┌───┐     ┌───┐
│   │     │   │     │   │     │ 3 │     │   │     │ 4 │
├───┤     ├───┤     ├───┤     ├───┤     ├───┤     ├───┤
│   │     │   │     │ 2 │     │ 2 │     │ 2 │     │ 2 │
├───┤     ├───┤     ├───┤     ├───┤     ├───┤     ├───┤
│   │     │ 1 │     │ 1 │     │ 1 │     │ 1 │     │ 1 │
└───┘     └───┘     └───┘     └───┘     └───┘     └───┘
empty     push 1    push 2    push 3    pop→3     push 4

연산 비용: 모두 O(1)
구현: 배열(끝에서만 push/pop) 또는 연결리스트 head
```

핵심: **top만 보고, top만 만진다**. 중간 원소 접근은 stack의 원래 의도 위반.

### 2.2 Monotonic Increasing Stack (값이 아래→위로 증가)

문제: 배열 `[2, 1, 5, 6, 2, 3]`에 대해 "각 원소의 다음으로 큰 원소"를 구하라.

**아이디어**: 답을 못 찾은 후보들을 stack에 보관. 새 원소가 들어올 때, stack top보다 크면 "top의 답은 이 새 원소!"라고 확정하고 pop. 새 원소 자체도 답을 기다리는 후보로 push.

```
배열 인덱스:  0   1   2   3   4   5
값:          [2,  1,  5,  6,  2,  3]
답(다음큰):    5   5   6  -1   3  -1

스텝별 stack (index 저장, 값은 참고용):

i=0, val=2
  stack empty → push 0
  stack: [0(=2)]                     bottom→top

i=1, val=1
  top val=2 > 1 → pop 없음, push 1
  stack: [0(=2), 1(=1)]              ← 위로 갈수록 감소 (monotonic decreasing in value)

i=2, val=5
  top val=1 < 5 → pop 1, ans[1]=5
  top val=2 < 5 → pop 0, ans[0]=5
  empty → push 2
  stack: [2(=5)]

i=3, val=6
  top val=5 < 6 → pop 2, ans[2]=6
  empty → push 3
  stack: [3(=6)]

i=4, val=2
  top val=6 > 2 → no pop, push 4
  stack: [3(=6), 4(=2)]

i=5, val=3
  top val=2 < 3 → pop 4, ans[4]=3
  top val=6 > 3 → push 5
  stack: [3(=6), 5(=3)]

끝나고 남은 인덱스 3, 5는 답이 없음 → ans[3]=-1, ans[5]=-1
```

**불변 조건 (invariant)**: 어느 순간이든, stack은 bottom→top으로 **단조 감소(값 기준)** 상태를 유지한다. 새로 들어오는 원소가 top보다 크면 pop으로 단조성을 회복한다.

**용어 혼동 주의**: "monotonic **increasing** stack"은 코드 작성자에 따라 다르게 부른다. 보통 **stack 위로 갈수록 값이 증가**(= "다음으로 작은 원소" 찾기)를 increasing이라 부르고, 위 예시처럼 **위로 갈수록 값이 감소**하면 decreasing이라 부른다. **방향을 외우지 말고**, "top과 새 원소 중 어느 쪽이 답을 확정짓는가"로 매 문제마다 생각하라.

### 2.3 Histogram Largest Rectangle — Monotonic Stack의 정점

문제: 막대 높이 `[2, 1, 5, 6, 2, 3]`. 인접한 막대들로 만들 수 있는 가장 큰 직사각형의 넓이를 구하라.

**핵심 통찰**: 어떤 막대 `h[i]`를 직사각형의 **높이**로 삼으면, 그 직사각형의 너비는 "왼쪽으로 `h[i]`보다 작아지는 첫 위치 +1" ~ "오른쪽으로 `h[i]`보다 작아지는 첫 위치 -1"이다. 두 경계를 monotonic stack으로 한 번에 구한다.

```
높이:  2  1  5  6  2  3
인덱스: 0  1  2  3  4  5

스택은 "아직 오른쪽 경계를 못 찾은, 위로 갈수록 값이 증가하는 막대 index"를 보관.

i=0, h=2
  empty → push 0
  stack: [0(=2)]

i=1, h=1
  top h=2 > 1 → pop 0, 그 때 0의 직사각형 결산:
    높이 = 2
    오른쪽 경계 = i = 1 (h=1이 처음으로 작거나 같아진 위치)
    왼쪽 경계 = stack 새 top (없으면 -1) = -1
    너비 = (1 - (-1) - 1) = 1
    넓이 = 2 × 1 = 2 ✓
  stack empty → push 1
  stack: [1(=1)]

i=2, h=5
  top h=1 < 5 → 그대로 push
  stack: [1(=1), 2(=5)]

i=3, h=6
  top h=5 < 6 → push
  stack: [1(=1), 2(=5), 3(=6)]

i=4, h=2
  top h=6 > 2 → pop 3, 결산:
    높이 = 6, 오른쪽 = 4, 왼쪽 = 2
    너비 = 4 - 2 - 1 = 1, 넓이 = 6 ✓
  top h=5 > 2 → pop 2, 결산:
    높이 = 5, 오른쪽 = 4, 왼쪽 = 1
    너비 = 4 - 1 - 1 = 2, 넓이 = 10 ✓ ★
  top h=1 < 2 → push
  stack: [1(=1), 4(=2)]

i=5, h=3
  top h=2 < 3 → push
  stack: [1(=1), 4(=2), 5(=3)]

배열 끝. 남은 막대 처리를 위해 가상의 h=0을 i=6 위치에 둔다고 가정:
  pop 5(h=3): 너비 = 6-4-1=1, 넓이 = 3
  pop 4(h=2): 너비 = 6-1-1=4, 넓이 = 8
  pop 1(h=1): 너비 = 6-(-1)-1=6, 넓이 = 6

최대 넓이 = 10
```

**왜 stack 위로 갈수록 값이 증가하는가?** 새 막대 `h[i]`가 들어올 때, top이 더 크면 "top의 오른쪽 경계가 i로 확정"되므로 결산하고 pop. 작거나 같으면 그대로 push. 이 invariant 덕에 각 막대는 정확히 1번 push, 1번 pop → **O(n)**.

**가상 sentinel `h=0` 트릭**: 마지막 막대들이 영원히 결산 안 되는 문제를 피하기 위해, 배열 끝에 0을 가상으로 두거나 루프 종료 후 별도 처리한다.

### 2.4 Decode String 시각화

입력: `"3[a2[c]]"` → 출력: `"accaccacc"`.

```
두 개의 stack: numStack(반복 횟수), strStack(직전 문자열)
현재 빌더 cur, 현재 숫자 num

읽기   numStack   strStack    cur     num   비고
'3'    []         []          ""      3
'['    [3]        [""]        ""      0     '['에서 둘 다 push, 초기화
'a'    [3]        [""]        "a"     0
'2'    [3]        [""]        "a"     2
'['    [3,2]      ["", "a"]   ""      0     중첩 [
'c'    [3,2]      ["", "a"]   "c"     0
']'    [3]        [""]        "ac"    0     pop "a", cur = "a" + ("c"×2) = "acc"... 잠깐
                                            정확히는: prev = pop strStack = "a"
                                                      k = pop numStack = 2
                                                      cur = prev + cur×k = "a" + "cc" = "acc"
']'    []         []          "accaccacc"   pop "", pop 3
                                            cur = "" + "acc"×3 = "accaccacc"
```

이 그림이 머릿속에 있으면 nested 표현 파싱 문제는 다 같은 패턴.

---

## 3. 직관과 정의

### 3.1 LIFO 한 줄 비유

> 카페테리아 쟁반 더미. 가장 위에 올린 쟁반을 가장 먼저 가져간다.

### 3.2 형식 정의

자료구조 `S`에 대해 다음 연산을 O(1)에 지원하면 stack이다.

- `push(x)`: top 위에 x를 올림
- `pop()`: top을 제거하고 반환
- `peek() / top()`: top을 반환만
- `isEmpty()`, `size()`

추가 연산이 붙으면 더 이상 순수 stack이 아니다 (예: Min Stack은 보조 stack 1개 더).

### 3.3 Monotonic Stack 불변 조건

**Monotonic stack**은 push/pop 규칙을 추가한 stack이다.

| 종류 | 불변 | 용도 |
|---|---|---|
| **Monotonic increasing** (위로 갈수록 값 증가) | 새 원소가 top ≤ 이면 그대로 push, 그 외 pop 반복 | 각 원소의 "다음/이전 작은 원소" 찾기, 히스토그램 |
| **Monotonic decreasing** (위로 갈수록 값 감소) | 새 원소가 top ≥ 이면 그대로 push, 그 외 pop 반복 | 각 원소의 "다음/이전 큰 원소" 찾기 (Daily Temperatures, NGE) |

**핵심 통찰**: monotonic stack을 거치는 동안 **각 원소는 정확히 1번 push되고 최대 1번 pop된다**. 이게 amortized O(n)의 이유. 보이는 코드는 이중 루프지만 총 작업량은 선형.

**무엇을 저장할 것인가 — 값 vs 인덱스?**
- 값 자체로 충분하면 값 저장 (수식 평가)
- **거리/너비**가 필요하면 무조건 **인덱스 저장** (Daily Temperatures, Histogram). 값은 `nums[stack.peek()]`로 조회.

### 3.4 Java: `Stack` 클래스 vs `Deque` — 왜 Stack을 피해야 하나

```java
// 안티 패턴 (Java 1.0 유산)
Stack<Integer> s = new Stack<>();

// 권장 (Java 6+)
Deque<Integer> s = new ArrayDeque<>();
```

| 항목 | `java.util.Stack` | `Deque` (`ArrayDeque`) |
|---|---|---|
| 상속 | `extends Vector` (synchronized) | `Deque` interface |
| 동기화 | 모든 op이 synchronized → 단일 thread도 비용 부담 | 비동기 |
| 순회 순서 | bottom→top (LIFO인데 iterator는 FIFO 순서) — 헷갈림 | top→bottom (`iterator()`) — 직관적 |
| 성능 | Vector resize + lock overhead | array 기반, lock zero |
| 공식 권고 | Javadoc에 "더 완전한 LIFO는 `Deque`" 명시 | 표준 |

**Joshua Bloch & Josh Bloch의 Effective Java**도 동일 결론. `Stack`은 Java 초기 잘못된 설계(`Vector` 상속)의 잔재. 모든 면접 코드는 `Deque<E> s = new ArrayDeque<>();`로 시작하라.

**ArrayDeque의 stack 매핑**:
- push: `push(x)` 또는 `addFirst(x)` 또는 `offerFirst(x)`
- pop: `pop()` 또는 `removeFirst()` 또는 `pollFirst()` (poll은 empty면 null)
- peek: `peek()` 또는 `peekFirst()`

`null`을 stack에 넣지 말라 (poll/peek의 null 반환과 구분 불가). 면접관이 흔히 물어보는 함정.

**LinkedList도 Deque 구현체지만 ArrayDeque보다 느림** (Node alloc, cache miss). 특별한 이유 없으면 ArrayDeque.

---

## 4. Java 템플릿 4종

### 4.1 괄호 매칭 (Valid Parentheses)

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;

class Solution {
    public boolean isValid(String s) {
        Deque<Character> stack = new ArrayDeque<>();
        Map<Character, Character> pair = Map.of(')', '(', ']', '[', '}', '{');

        for (char c : s.toCharArray()) {
            if (c == '(' || c == '[' || c == '{') {
                stack.push(c);
            } else {
                // 닫는 괄호: stack이 비어있거나, top이 짝이 아니면 false
                if (stack.isEmpty() || stack.pop() != pair.get(c)) {
                    return false;
                }
            }
        }
        return stack.isEmpty();  // 모든 여는 괄호가 닫혔어야 함
    }
}
```

**왜 isEmpty 체크 먼저?** stack이 비어있는데 `pop()`하면 `NoSuchElementException`. 면접관이 가장 자주 트는 함정.

**왜 마지막에 isEmpty 체크?** `"(("` 같이 닫힌 적 없는 경우 false. for 루프 통과만으로는 부족.

### 4.2 Monotonic Stack — Next Greater Element / Daily Temperatures

```java
import java.util.ArrayDeque;
import java.util.Deque;

class Solution {
    // 각 날짜에 대해, 며칠 후에 더 따뜻한 날이 오는지 (없으면 0)
    public int[] dailyTemperatures(int[] T) {
        int n = T.length;
        int[] ans = new int[n];
        Deque<Integer> stack = new ArrayDeque<>();  // index 저장, 위로 갈수록 T 값 감소

        for (int i = 0; i < n; i++) {
            // 새 원소 T[i]가 top보다 크면 top의 답 확정
            while (!stack.isEmpty() && T[stack.peek()] < T[i]) {
                int j = stack.pop();
                ans[j] = i - j;
            }
            stack.push(i);
        }
        // 끝까지 답 못 찾은 index는 ans[i] = 0 (배열 기본값)
        return ans;
    }
}
```

**불변**: stack은 bottom→top으로 T 값이 단조 감소 (위로 갈수록 작은 값). 새 i가 들어와 top의 T보다 크면 → top의 next greater = i → pop.

**왜 인덱스 저장?** 거리(`i - j`)가 필요하므로. 값만 있으면 거리 계산 불가.

### 4.3 Largest Rectangle in Histogram

```java
import java.util.ArrayDeque;
import java.util.Deque;

class Solution {
    public int largestRectangleArea(int[] heights) {
        int n = heights.length;
        Deque<Integer> stack = new ArrayDeque<>();  // index, 위로 갈수록 height 증가
        int maxArea = 0;

        for (int i = 0; i <= n; i++) {
            // i == n은 가상 sentinel (높이 0)
            int curH = (i == n) ? 0 : heights[i];

            while (!stack.isEmpty() && heights[stack.peek()] > curH) {
                int h = heights[stack.pop()];
                // pop 후의 새 top이 왼쪽 경계 (없으면 -1)
                int leftBound = stack.isEmpty() ? -1 : stack.peek();
                int width = i - leftBound - 1;
                maxArea = Math.max(maxArea, h * width);
            }
            stack.push(i);
        }
        return maxArea;
    }
}
```

**가상 sentinel 트릭**: `i <= n`까지 돌고, `i == n`일 때 `curH = 0`으로 두면 남은 모든 막대가 자동 결산. 별도 cleanup 루프 불필요 → 코드 짧고 버그 적음.

**왜 strict `>` 인가?** 같은 높이일 때 누가 먼저 결산되든 최대값은 같으므로 `≥`도 정답. 단 `>`가 일반적 관습 (불필요한 pop 회피).

### 4.4 Decode String

```java
import java.util.ArrayDeque;
import java.util.Deque;

class Solution {
    public String decodeString(String s) {
        Deque<Integer> numStack = new ArrayDeque<>();
        Deque<StringBuilder> strStack = new ArrayDeque<>();
        StringBuilder cur = new StringBuilder();
        int k = 0;

        for (char c : s.toCharArray()) {
            if (Character.isDigit(c)) {
                k = k * 10 + (c - '0');  // 두 자리 이상 처리
            } else if (c == '[') {
                numStack.push(k);
                strStack.push(cur);
                k = 0;
                cur = new StringBuilder();
            } else if (c == ']') {
                int repeat = numStack.pop();
                StringBuilder prev = strStack.pop();
                for (int i = 0; i < repeat; i++) prev.append(cur);
                cur = prev;
            } else {
                cur.append(c);
            }
        }
        return cur.toString();
    }
}
```

**왜 stack 2개?** 중첩된 `[`마다 "지금까지의 문자열"과 "다음에 곱해질 횟수"를 별도로 보관해야 함. 한 stack에 섞으면 타입 혼란.

**왜 `k = k * 10 + (c - '0')`?** `"100[a]"` 같은 두 자리 이상 숫자 처리. 이걸 빼먹어서 `1`, `0`, `0`을 따로 push하면 버그.

---

## 5. Kotlin 템플릿 4종

Kotlin은 `java.util.ArrayDeque`를 `kotlin.collections.ArrayDeque`로도 쓸 수 있다 (Kotlin 1.4+). API가 조금 다르다.

| 동작 | Kotlin ArrayDeque |
|---|---|
| push | `addLast(x)` 또는 `addFirst(x)` (front를 top으로 쓸지 결정) |
| pop | `removeLast()` 또는 `removeFirst()` |
| peek | `last()` / `first()` |
| empty 체크 | `isEmpty()` |

**관습**: Kotlin에선 보통 `addLast/removeLast/last()`로 stack을 모델링한다 (배열 끝이 top). Java의 `push/pop` 의미와 정반대지만, ArrayDeque 내부 구현상 동등 비용.

### 5.1 괄호 매칭

```kotlin
class Solution {
    fun isValid(s: String): Boolean {
        val stack = ArrayDeque<Char>()
        val pair = mapOf(')' to '(', ']' to '[', '}' to '{')

        for (c in s) {
            if (c in "([{") {
                stack.addLast(c)
            } else {
                if (stack.isEmpty() || stack.removeLast() != pair[c]) return false
            }
        }
        return stack.isEmpty()
    }
}
```

### 5.2 Daily Temperatures

```kotlin
class Solution {
    fun dailyTemperatures(T: IntArray): IntArray {
        val n = T.size
        val ans = IntArray(n)
        val stack = ArrayDeque<Int>()  // index, 위로 갈수록 T 감소

        for (i in 0 until n) {
            while (stack.isNotEmpty() && T[stack.last()] < T[i]) {
                val j = stack.removeLast()
                ans[j] = i - j
            }
            stack.addLast(i)
        }
        return ans
    }
}
```

### 5.3 Largest Rectangle

```kotlin
class Solution {
    fun largestRectangleArea(heights: IntArray): Int {
        val n = heights.size
        val stack = ArrayDeque<Int>()
        var maxArea = 0

        for (i in 0..n) {
            val curH = if (i == n) 0 else heights[i]
            while (stack.isNotEmpty() && heights[stack.last()] > curH) {
                val h = heights[stack.removeLast()]
                val leftBound = if (stack.isEmpty()) -1 else stack.last()
                val width = i - leftBound - 1
                maxArea = maxOf(maxArea, h * width)
            }
            stack.addLast(i)
        }
        return maxArea
    }
}
```

### 5.4 Decode String

```kotlin
class Solution {
    fun decodeString(s: String): String {
        val numStack = ArrayDeque<Int>()
        val strStack = ArrayDeque<StringBuilder>()
        var cur = StringBuilder()
        var k = 0

        for (c in s) {
            when {
                c.isDigit() -> k = k * 10 + (c - '0')
                c == '[' -> {
                    numStack.addLast(k); strStack.addLast(cur)
                    k = 0; cur = StringBuilder()
                }
                c == ']' -> {
                    val repeat = numStack.removeLast()
                    val prev = strStack.removeLast()
                    repeat(repeat) { prev.append(cur) }
                    cur = prev
                }
                else -> cur.append(c)
            }
        }
        return cur.toString()
    }
}
```

---

## 6. 시간/공간 복잡도

### 6.1 Basic Stack

| 연산 | 시간 |
|---|---|
| push / pop / peek | O(1) (ArrayDeque resize amortized O(1)) |
| search | O(n) — 원래 stack의 의도 아님 |

### 6.2 Monotonic Stack — 왜 amortized O(n)인가

```
보이는 코드:
  for i in 0..n:                ← n번
    while stack.top과 비교 → pop ← 안쪽 루프
    push i

순진하게 보면 O(n²). 실제로는 O(n). 왜?

회계적 증명 (amortized analysis):
  각 원소 i는 정확히 1번 push된다.
  pop되는 횟수는 최대 1번 (pop 후 영원히 stack 밖).

  → 총 push 횟수 = n
  → 총 pop 횟수 ≤ n
  → 총 작업량 ≤ 2n = O(n)

while 루프가 한 iteration에서 k번 돌더라도, 그 k번의 pop은 이전 push들의 비용을
"미리 지불해둔" 셈. 한 원소당 평균 비용은 상수.
```

**이 amortized 분석은 라이브 코딩 단골 질문**. "이중 루프인데 왜 O(n²)이 아닌가요?"에 위 문장 그대로 답할 수 있어야 한다.

**공간**: stack 최대 크기 = n (worst case 모든 원소가 monotonic하게 들어옴). 따라서 O(n).

### 6.3 Histogram

- 시간: O(n) (각 막대 1번 push, 1번 pop)
- 공간: O(n) (worst case 모두 증가 수열)

### 6.4 Decode String

- 시간: O(N) where N = decoded 길이 (각 문자가 정확히 1번 append됨)
- 공간: O(N) (cur + stack)

**함정**: 입력 길이가 짧아도 decoded 결과가 천문학적일 수 있음. `"10[10[10[a]]]"` = 1000자. 시간 복잡도 분석 시 항상 **출력 크기**를 명시해야 한다.

---

## 7. 대표 문제 8개

### 7.1 LeetCode 20 — Valid Parentheses

**문제**: `()`, `[]`, `{}` 만으로 된 문자열이 valid한가? 모든 여는 괄호는 같은 종류의 닫는 괄호로, 올바른 순서로 닫혀야 함.

**접근**: stack에 여는 괄호 push, 닫는 괄호가 오면 top과 짝 비교.

**풀이**: §4.1 참조.

**복잡도**: O(n) 시간, O(n) 공간.

**함정**:
- 빈 stack에서 pop 시도 (`")"` 입력) → isEmpty 먼저 체크
- 끝에 stack 안 비었는지 체크 안 함 → `"(("` false 못 잡음
- char 비교를 `==` 대신 `.equals()`로 (Java)? char는 primitive, `==` 맞음

### 7.2 LeetCode 155 — Min Stack

**문제**: push, pop, top, **getMin** 모두 O(1)인 stack 설계.

**접근**: 보조 stack에 "현재 시점의 최소값"을 함께 유지. push 시 새 값과 보조 top 중 작은 값을 보조에도 push. pop 시 양쪽 모두 pop.

**Java**:
```java
import java.util.ArrayDeque;
import java.util.Deque;

class MinStack {
    private final Deque<Integer> data = new ArrayDeque<>();
    private final Deque<Integer> mins = new ArrayDeque<>();

    public void push(int val) {
        data.push(val);
        mins.push(mins.isEmpty() ? val : Math.min(val, mins.peek()));
    }

    public void pop() {
        data.pop();
        mins.pop();
    }

    public int top() {
        return data.peek();
    }

    public int getMin() {
        return mins.peek();
    }
}
```

**Kotlin**:
```kotlin
class MinStack {
    private val data = ArrayDeque<Int>()
    private val mins = ArrayDeque<Int>()

    fun push(`val`: Int) {
        data.addLast(`val`)
        mins.addLast(if (mins.isEmpty()) `val` else minOf(`val`, mins.last()))
    }
    fun pop() { data.removeLast(); mins.removeLast() }
    fun top(): Int = data.last()
    fun getMin(): Int = mins.last()
}
```

**복잡도**: 모두 O(1) 시간, O(n) 공간.

**최적화 (꼬리질문)**: 메모리를 절반으로 줄이려면 — mins에 매번 push하지 말고, "새 값 ≤ 현재 min"일 때만 push. pop 시 "data top == mins top"이면 mins도 pop.

```java
public void push(int val) {
    data.push(val);
    if (mins.isEmpty() || val <= mins.peek()) mins.push(val);
}
public void pop() {
    int v = data.pop();
    if (v == mins.peek()) mins.pop();
}
```

**함정**: `≤`이지 `<` 아님. 같은 최소값이 여러 개 push되면 각각 mins에 들어가야 동시 pop 시 정확. `<`로 하면 같은 최소값 하나만 pop했을 때 mins가 잘못된 값을 가리킴.

### 7.3 LeetCode 739 — Daily Temperatures (Monotonic Stack)

**문제**: 각 날짜에 대해, 며칠 후에 더 따뜻한 날이 오는지. 없으면 0.

**접근**: §4.2 그대로. monotonic decreasing stack (위로 갈수록 작은 T).

**풀이**: §4.2 참조.

**복잡도**: O(n) 시간 (amortized), O(n) 공간.

**함정**:
- 값이 아닌 **인덱스** 저장 (거리 필요)
- `<=` vs `<` — 같은 온도는 "더 따뜻한" 아님, strict `<`로 비교 (`T[stack.peek()] < T[i]`만 pop). 등호 처리 한 글자 실수가 자주 나옴.

### 7.4 LeetCode 84 — Largest Rectangle in Histogram

**문제**: 막대 배열에서 인접한 막대로 만들 수 있는 가장 큰 직사각형 넓이.

**접근**: §4.3 그대로.

**풀이**: §4.3 참조.

**복잡도**: O(n) 시간, O(n) 공간.

**함정**:
- 마지막에 남은 막대 처리를 안 함 → 가상 sentinel `h=0` 필수
- `leftBound = stack.peek()`을 pop **전**에 읽어버리는 실수 → 항상 pop 후의 새 top이 leftBound
- 너비 계산 off-by-one: `i - leftBound - 1` (양쪽 끝 포함하지 않는 거리)

**연결**: Maximal Rectangle (LeetCode 85)는 각 row마다 histogram으로 환원해 이 알고리즘을 n번 호출 → O(m×n).

### 7.5 LeetCode 503 — Next Greater Element II (원형 배열)

**문제**: 원형 배열에서 각 원소의 next greater.

**접근**: 배열을 2배로 가상 확장 (`i = 0..2n-1`, 실제 인덱스는 `i % n`). monotonic stack은 동일.

**Java**:
```java
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Deque;

class Solution {
    public int[] nextGreaterElements(int[] nums) {
        int n = nums.length;
        int[] ans = new int[n];
        Arrays.fill(ans, -1);
        Deque<Integer> stack = new ArrayDeque<>();  // index in [0, n)

        for (int i = 0; i < 2 * n; i++) {
            int idx = i % n;
            while (!stack.isEmpty() && nums[stack.peek()] < nums[idx]) {
                ans[stack.pop()] = nums[idx];
            }
            // 두 번째 사이클에선 push하지 않음 (이미 답을 못 찾은 게 확정)
            if (i < n) stack.push(idx);
        }
        return ans;
    }
}
```

**Kotlin**:
```kotlin
class Solution {
    fun nextGreaterElements(nums: IntArray): IntArray {
        val n = nums.size
        val ans = IntArray(n) { -1 }
        val stack = ArrayDeque<Int>()
        for (i in 0 until 2 * n) {
            val idx = i % n
            while (stack.isNotEmpty() && nums[stack.last()] < nums[idx]) {
                ans[stack.removeLast()] = nums[idx]
            }
            if (i < n) stack.addLast(idx)
        }
        return ans
    }
}
```

**복잡도**: O(n) 시간 (2n 순회), O(n) 공간.

**함정**: 두 번째 사이클에선 push 금지. 안 그러면 같은 인덱스가 중복으로 들어가 무한 루프 위험.

### 7.6 LeetCode 32 — Longest Valid Parentheses

**문제**: `"(()"`처럼 섞인 문자열에서 valid한 연속 부분 문자열의 최대 길이.

**접근 (stack)**: stack에 **인덱스** 저장. 초기값으로 `-1`을 sentinel로 push (왼쪽 경계).

- `'('` → push index
- `')'` → pop. 그 후 stack이 비면 현재 인덱스를 sentinel로 push (새 base). 안 비면 현재 길이 = `i - stack.peek()`.

**Java**:
```java
import java.util.ArrayDeque;
import java.util.Deque;

class Solution {
    public int longestValidParentheses(String s) {
        Deque<Integer> stack = new ArrayDeque<>();
        stack.push(-1);  // sentinel: "직전 unmatched 위치"
        int max = 0;

        for (int i = 0; i < s.length(); i++) {
            if (s.charAt(i) == '(') {
                stack.push(i);
            } else {
                stack.pop();
                if (stack.isEmpty()) {
                    stack.push(i);  // 새 sentinel
                } else {
                    max = Math.max(max, i - stack.peek());
                }
            }
        }
        return max;
    }
}
```

**Kotlin**:
```kotlin
class Solution {
    fun longestValidParentheses(s: String): Int {
        val stack = ArrayDeque<Int>()
        stack.addLast(-1)
        var max = 0
        for (i in s.indices) {
            if (s[i] == '(') stack.addLast(i)
            else {
                stack.removeLast()
                if (stack.isEmpty()) stack.addLast(i)
                else max = maxOf(max, i - stack.last())
            }
        }
        return max
    }
}
```

**복잡도**: O(n) 시간, O(n) 공간.

**함정**:
- `-1` sentinel 빠뜨림 → 첫 매칭 길이 계산 off-by-one
- `pop 후 isEmpty` 분기 누락 → `")"` 처리 시 NSE

**다른 풀이들**: DP (O(n) 시간 O(n) 공간), 양방향 카운터 (O(n) 시간 O(1) 공간). 면접에선 stack 풀이가 가장 일반화 잘 됨.

### 7.7 LeetCode 394 — Decode String

**문제**: `"3[a2[c]]"` → `"accaccacc"`.

**접근**: §4.4 그대로.

**풀이**: §4.4 참조.

**복잡도**: O(N) (N = decoded 길이).

**함정**:
- 두 자리 숫자 (`"10[a]"`) 처리 — `k = k*10 + digit`
- 중첩 처리 — stack 2개 (숫자용/문자열용)
- `cur`을 매번 `new StringBuilder()` 안 하면 이전 결과 오염

### 7.8 프로그래머스 — 주식가격 / 짝지어 제거하기 / 같은 숫자는 싫어

**(a) 주식가격** — 각 시점의 가격이 떨어지지 않은 기간(초)을 구하라.

**접근**: monotonic stack의 변형. stack에 인덱스 저장, top의 price > 새 price면 pop하면서 거리 결산.

**Java**:
```java
import java.util.ArrayDeque;
import java.util.Deque;

class Solution {
    public int[] solution(int[] prices) {
        int n = prices.length;
        int[] ans = new int[n];
        Deque<Integer> stack = new ArrayDeque<>();

        for (int i = 0; i < n; i++) {
            while (!stack.isEmpty() && prices[stack.peek()] > prices[i]) {
                int j = stack.pop();
                ans[j] = i - j;
            }
            stack.push(i);
        }
        // 끝까지 안 떨어진 가격들은 (n-1) - j
        while (!stack.isEmpty()) {
            int j = stack.pop();
            ans[j] = (n - 1) - j;
        }
        return ans;
    }
}
```

**복잡도**: O(n).

**함정**: 끝까지 안 떨어진 가격 처리 잊지 말 것 (`while (!stack.isEmpty())` cleanup).

**(b) 짝지어 제거하기** — 같은 두 글자가 인접하면 제거. 전부 제거 가능한가?

**Java**:
```java
import java.util.ArrayDeque;
import java.util.Deque;

class Solution {
    public int solution(String s) {
        Deque<Character> stack = new ArrayDeque<>();
        for (char c : s.toCharArray()) {
            if (!stack.isEmpty() && stack.peek() == c) stack.pop();
            else stack.push(c);
        }
        return stack.isEmpty() ? 1 : 0;
    }
}
```

**복잡도**: O(n).

**핵심 통찰**: stack은 **연속 중복 제거의 최적 자료구조**. `"baabaa"` → b, ba, b(ba pop), 다시 같은 패턴.

**(c) 같은 숫자는 싫어** — 연속된 같은 숫자를 하나만 남기기.

**Java**:
```java
import java.util.ArrayDeque;
import java.util.Deque;

class Solution {
    public int[] solution(int[] arr) {
        Deque<Integer> stack = new ArrayDeque<>();
        for (int x : arr) {
            if (stack.isEmpty() || stack.peek() != x) stack.push(x);
        }
        // bottom→top 순서로 결과 반환 (LinkedList의 descendingIterator 활용)
        int[] result = new int[stack.size()];
        for (int i = result.length - 1; i >= 0; i--) result[i] = stack.pop();
        return result;
    }
}
```

**복잡도**: O(n).

**Kotlin 한 줄 버전** (stack 안 써도 됨, 단순 사례):
```kotlin
fun solution(arr: IntArray): IntArray =
    arr.toList().zipWithNext().filter { it.first != it.second }
        .map { it.first } .plus(arr.last()).toIntArray()
```

면접에선 stack 풀이를 보여주는 게 패턴 학습 의도에 부합.

---

## 8. 함정·엣지케이스 체크리스트

면접 코드 작성 후 제출 전 반드시 점검할 항목.

| # | 함정 | 증상 | 해결 |
|---|---|---|---|
| 1 | 빈 stack에서 pop/peek | `NoSuchElementException` | 항상 `isEmpty()` 먼저 |
| 2 | `Stack` 클래스 사용 | synchronized overhead, iterator 순서 헷갈림 | `Deque + ArrayDeque` |
| 3 | `null` push | `peek()` 결과 null이 "empty" 인지 "값" 인지 모호 | null 금지 |
| 4 | 값 저장 vs 인덱스 저장 혼동 | 거리 계산 불가, off-by-one | "거리/너비 필요 → 인덱스" |
| 5 | monotonic 방향 잘못 잡음 | "다음 큰" 찾는데 increasing stack 사용 | 매 문제마다 "어느 쪽이 답을 확정짓는가" 그려보기 |
| 6 | strict `<` vs `≤` 혼동 | 같은 값 처리에서 답 다름 | Daily Temperatures는 strict `<` (등온은 "더 따뜻" 아님) |
| 7 | 끝까지 답 못 찾은 원소 누락 | ans 일부가 default 0/-1로 남음 | sentinel 트릭 또는 cleanup 루프 |
| 8 | mutable 상태 공유 | `for (int x : list) stack.push(x)` 후 list 수정 시 stack 영향? (primitive면 무관, 객체면 ref 공유 주의) | immutable 또는 deep copy |
| 9 | StringBuilder를 stack에 넣고 외부에서 mutate | decode string 변형에서 자주 발생 | 매 단계 새 SB 생성 |
| 10 | 재귀 깊이 vs 명시 stack | 입력 큰 경우 재귀 stack overflow | 명시 stack으로 변환 |
| 11 | 두 자리 이상 숫자 파싱 누락 | `"10[a]"` 결과 틀림 | `k = k*10 + digit` |
| 12 | sentinel 값 빠뜨림 | Longest Valid Parens에서 `-1` 안 넣음 | base index 명시 |

---

## 9. 꼬리질문 트리

면접관이 stack 문제 통과 후 던질 확률 높은 follow-up.

### Q1. Stack을 큐 2개로 구현하라 (LeetCode 225)

**접근 A (push O(n))**: queue1에 새 원소를 넣을 때, 기존 queue1 내용을 모두 queue2로 옮긴 뒤 새 원소를 queue1에 push, 그 다음 queue2를 queue1으로 다시 옮김. 결과: queue1 head가 항상 stack의 top.

**접근 B (push O(1), pop O(n))**: push는 그냥 queue1 enqueue. pop은 queue1 마지막 직전까지 queue2로 옮기고 마지막 원소 반환.

**한 단락 답**: 큐 2개로 stack을 만드려면 한쪽 op의 비용을 O(n)으로 옮겨야 함 (push-heavy면 B, pop-heavy면 A). 진짜 O(1)은 큐 1개 + 회전 트릭으로도 가능: `push` 시 큐에 enqueue 후 큐 크기만큼 회전 (front를 뒤로) → front가 top.

### Q2. Queue를 스택 2개로 구현하라 (LeetCode 232)

**접근 (amortized O(1))**: inStack, outStack 두 개. enqueue는 inStack push. dequeue는 outStack이 비었으면 inStack을 모두 옮긴 뒤 outStack pop, 안 비었으면 그냥 outStack pop.

**왜 amortized O(1)?** 각 원소는 정확히 1번 inStack 진입, 1번 inStack→outStack 이동, 1번 outStack 이탈 → 평생 3번 → O(1).

**Java 코드**:
```java
class MyQueue {
    private Deque<Integer> in = new ArrayDeque<>();
    private Deque<Integer> out = new ArrayDeque<>();

    public void push(int x) { in.push(x); }
    public int pop() { move(); return out.pop(); }
    public int peek() { move(); return out.peek(); }
    public boolean empty() { return in.isEmpty() && out.isEmpty(); }

    private void move() {
        if (out.isEmpty()) while (!in.isEmpty()) out.push(in.pop());
    }
}
```

### Q3. 재귀를 명시 스택으로 어떻게 변환?

**한 단락 답**: 함수 호출 = stack frame push, return = pop. 각 호출의 **로컬 변수 + 진행 상태(어디까지 진행했는지)**를 frame 객체로 묶어 명시 stack에 넣는다. while loop으로 stack이 빌 때까지 처리. iterative DFS(`stack.push(start); while(!stack.isEmpty()) { node = stack.pop(); for (next : node.adj) stack.push(next); }`)가 가장 단순한 예. inorder traversal처럼 "왼쪽 끝까지 간 후 자신 처리, 그 다음 오른쪽"같이 중간에 작업이 끼면 frame에 "진행 단계"를 명시해야 한다.

**왜 변환?** 입력이 깊으면 (e.g. linked list 100만 노드, skewed tree depth 10000) JVM의 thread stack (보통 512KB ~ 1MB, `-Xss`)이 터져 `StackOverflowError`. 명시 stack은 heap에 살아 훨씬 큼.

### Q4. Min Stack을 진짜 O(1)에 모든 op + 메모리도 최적화?

**답**: §7.2의 최적화 — 보조 stack에 `≤ min`일 때만 push, pop 시 `data top == mins top`일 때만 mins pop. 메모리는 worst case 여전히 O(n) (감소 수열 입력)이지만 평균은 절감.

**더 줄이려면?** 보조 stack 없이 단일 stack에 `(value, currentMin)` 쌍 저장. 본질은 동일, 객체 alloc 비용 vs 보조 stack의 메모리 trade-off.

**O(1)이 아닌 변형**: getMedian, getMax가 동시에 필요하면? → median은 heap 2개 (다른 챕터), max만이면 max stack도 동일 아이디어.

### Q5. 스레드 안전한 stack이 필요하면?

**답**:
- `ConcurrentLinkedDeque` — lock-free deque, push/pop O(1).
- `java.util.concurrent.LinkedBlockingDeque` — blocking 필요 시.
- `Stack` 클래스는 synchronized지만 throughput 낮음, 추천 안 함.
- 실전 라이브 코딩에선 동시성 stack을 요구하는 경우 드물지만, 시스템 디자인 면접에선 단골.

### Q6. monotonic stack을 deque로 확장하면?

**답**: **Monotonic Deque** (양쪽에서 pop 가능) — Sliding Window Maximum (LeetCode 239)의 표준 해법. 윈도우를 벗어난 인덱스를 front에서 pop, 새 원소보다 작은 인덱스를 back에서 pop. 02-sliding-window 챕터에서 다룸.

핵심 차이: monotonic stack은 한쪽 끝(top)에서만 조작 → "오른쪽으로만 진행". monotonic deque는 양쪽 → "윈도우 양 끝 관리".

### Q7. Stack 깊이가 폭주하면? Production 진단?

**답**: thread dump에서 같은 패턴의 stack frame이 수천 개 쌓여 있으면 무한 재귀. 자주 보는 케이스:
- JSON parser가 cyclic reference 만나 무한 재귀
- 잘못된 DI cycle (Spring `BeanCurrentlyInCreationException`이 안 잡힐 때)
- ORM에서 `toString()` cyclic (Entity A → B → A → ...)

해결: `-Xss`로 늘리는 건 임시방편. 근본 해결은 재귀 종료 조건 점검 + cycle detection (visited set, IdentityHashMap).

---

## 10. 다른 패턴과의 연결

```
                       Stack 패턴 (이 챕터)
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
       Basic Stack      Monotonic Stack    재귀 = 호출 스택
            │                 │                 │
            ▼                 ▼                 ▼
    괄호 매칭, parsing  NGE, Histogram,    DFS, Backtracking,
    Decode String     Daily Temp        Iterative Tree 순회
                              │                 │
                              ▼                 ▼
                       Monotonic Deque    Iterative DFS/inorder
                       (Sliding Window     (재귀 → 명시 stack)
                        Maximum 등)              │
                                                ▼
                                         JVM 호출 스택과 동형
```

**(1) DFS의 재귀 = 스택**: 재귀 호출이 곧 함수 호출 stack에 frame을 쌓는 것. iterative DFS는 그 frame을 heap의 명시 stack(`Deque`)으로 옮긴 것. 08-dfs 챕터에서 본격 다룬다.

**(2) Monotonic Deque = Monotonic Stack의 양방향 확장**: 윈도우 양쪽 끝 관리가 필요할 때. Sliding Window Maximum (02 챕터).

**(3) Backtracking**: 선택 → 재귀 → 되돌리기. "되돌리기"가 본질적으로 stack pop. 10-backtracking 챕터.

**(4) Parser/Compiler**: 표현식 평가 (Shunting Yard), AST 빌드, 모두 stack 기반. JVM의 `iadd`, `istore` 등 bytecode가 operand stack에서 동작.

**(5) Undo/Redo**: 두 개의 stack (undo stack, redo stack). 사용자 액션 push, undo 시 pop 후 redo로 옮김. IDE, 텍스트 에디터의 표준 패턴.

---

## 11. 시니어 운영 매핑 — Stack을 "production에서 안다"는 의미

| 영역 | Stack의 역할 | 시니어가 보는 것 |
|---|---|---|
| **JVM 함수 호출 스택** | thread마다 1개, frame = 로컬 + operand stack + PC | `StackOverflowError`, `-Xss` (보통 512KB ~ 1MB), thread dump 읽기 |
| **JVM operand stack** | bytecode `iload`/`iadd`/`istore`가 사용. method 단위 고정 크기 | `javap -c`로 bytecode 분석 시 stack depth 확인 |
| **Parser/Compiler** | 표현식 평가 (Shunting Yard), AST, syntax 검증 | regex `(`/`)` 검증, JSON nested depth 제한 (`Jackson MAX_NESTING_DEPTH`), YAML billion laughs 방어 |
| **Undo/Redo 시스템** | 두 stack (undo, redo). 액션을 명령 객체로 push | Command pattern, IntelliJ/VSCode undo, DB transaction rollback의 개념 모델 |
| **Web browser 뒤로/앞으로** | history stack | SPA의 `history.pushState`, back button UX |
| **Recursive call → trampoline** | 깊은 재귀 → heap 위 명시 stack | Scala TCO, 함수형 언어의 stack-safe 재귀 |
| **DB 트랜잭션 SAVEPOINT** | 중첩 트랜잭션의 LIFO 복구 지점 | PostgreSQL `SAVEPOINT s1; ... ROLLBACK TO s1;`, JPA `@Transactional(propagation = NESTED)` |
| **Exception unwinding** | exception 발생 시 frame을 LIFO로 pop하며 `finally`/catch 실행 | Java try-with-resources의 close 순서가 LIFO인 이유 |

**실전 진단 예시**:
- **증상**: 특정 endpoint에서 `StackOverflowError`. **의심**: 무한 재귀 또는 cyclic 자료구조. **진단**: thread dump → 같은 frame이 수천 개 반복 → 재귀 종료 조건 점검 + cycle 감지 (IdentityHashMap visited set).
- **증상**: JSON 파싱 시 OOM/StackOverflow. **의심**: 적대적 입력 (deeply nested). **해결**: parser max depth 설정 (Jackson `StreamReadConstraints`), input size 제한.
- **증상**: 디자인 면접에서 "undo 기능 설계해라". **답**: Command 객체 + undo stack + redo stack. 새 액션은 redo stack 비움.

**Stack이라는 단어를 들었을 때 머릿속에 자동으로 떠올라야 한다**: LIFO + push/pop O(1) + Deque/ArrayDeque + monotonic stack의 amortized O(n) + JVM 호출 스택 + parser/undo/transaction의 본질이 같다는 점.

---

## 부록 A. 한 화면 요약 (라이브 코딩 직전 복습용)

```
[Stack 한 페이지]

자료구조       Java: Deque<E> s = new ArrayDeque<>();
              Kotlin: val s = ArrayDeque<E>()
              push = push/addLast, pop = pop/removeLast, peek = peek/last()
              Stack 클래스 X (synchronized, Vector 상속)

언제 쓰나      "방금 본 것을 다음에 처음 본다" = LIFO
              괄호/짝짓기, undo, 파싱, decode, iterative DFS

Monotonic     "각 원소의 다음 큰/작은 원소" = monotonic stack
              불변: 위로 갈수록 단조 (증가 또는 감소)
              저장: 거리 필요하면 index, 아니면 value
              왜 O(n): 각 원소 push 1번, pop 최대 1번 = amortized

대표 문제      Valid Parentheses, Min Stack, Daily Temperatures,
              Largest Rectangle Histogram, Next Greater II,
              Longest Valid Parens, Decode String,
              주식가격/짝지어 제거/같은 숫자는 싫어

함정          빈 stack pop, null 금지, monotonic 방향, sentinel 누락,
              두 자리 숫자, strict < vs ≤, 끝까지 답 못 찾은 원소

연결          DFS 재귀, Monotonic Deque (sliding window),
              Backtracking, JVM 호출 stack
```

---

> Stack은 자료구조 중 가장 단순하지만, **monotonic stack**으로 가는 순간 라이브 코딩의 격이 달라진다. NGE, Daily Temperatures, Histogram을 백지에서 줄줄 그릴 수 있고, amortized O(n) 증명을 한 문장으로 말할 수 있고, `ArrayDeque` 한 줄로 시작할 수 있으면 — 이 패턴은 면접에서 안전지대다.
