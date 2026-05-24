# 06. Linked List — 노드와 화살표로 사고하기

> "Linked List? 노드 next로 잇는 거" 라고 답하면 입문자.
> 마스터는 **dummy head sentinel 트릭**으로 head 변경 분기를 없애고, **fast/slow pointer**로 한 패스에 중간/사이클/뒤에서 K번째를 동시에 잡고, **in-place reverse 3-pointer dance** (prev, cur, next)를 손가락 세 개로 그리며, **Floyd's tortoise & hare**가 왜 cycle 시작점까지 잡아내는지 수학적으로 설명한다.
>
> Linked List는 코딩 테스트에서 "포인터 조작 실력"을 보는 거의 유일한 패턴이다. 배열은 인덱스, Tree는 재귀, Graph는 인접 리스트로 추상화되지만 — Linked List는 **다음 노드를 어디로 가리키게 할지를 직접 손으로 그려야** 한다. 화이트보드 면접에서 "이 화살표가 어디로 가야 하지?" 라고 멈추는 순간 끝난다.

---

## 0. 인지 신호 — 이 패턴인지 30초 안에 판단

문제를 읽을 때 다음 신호 중 **하나라도** 보이면 Linked List 패턴이다.

| 신호 | 예시 문구 | 패턴 변형 |
|---|---|---|
| **ListNode 입력** | "singly linked list `head` 가 주어진다" | 기본 |
| **"뒤집기"** | "reverse the linked list", "구간 [m,n]을 뒤집어라" | reverse / reverse-between |
| **"중간 찾기"** | "find the middle node" | fast/slow pointer |
| **"뒤에서 K번째"** | "remove the Nth node from the end" | fast/slow with gap |
| **"사이클 검출"** | "determine if the list has a cycle" | Floyd's tortoise & hare |
| **"사이클 시작점"** | "return the node where the cycle begins" | Floyd + math |
| **"K개씩 묶어 뒤집기"** | "reverse nodes in k-group" | k-group reverse |
| **"두 정렬 리스트 병합"** | "merge two sorted lists" | dummy head + 2-pointer |
| **"회문 검사"** | "is the list a palindrome?" | 중간 분할 + reverse + 비교 |
| **"deep copy with random pointer"** | "copy list with random pointer" | hash map OR weaving |

### 0.1 다른 패턴과의 구분

- **Array two-pointer vs Linked list two-pointer**: 배열은 index 산술 (`left++`, `right--`), 리스트는 노드 hop (`slow=slow.next`). 같은 "두 포인터" 사상이지만 **랜덤 액세스 불가**가 결정적 차이.
- **Stack/Heap의 구현 자료구조 vs Linked List 문제**: Stack은 linked list로 만들 수 있지만 (push/pop만), 문제로 나오면 "노드 조작" 자체가 핵심.
- **Tree vs Linked List**: tree는 자식이 여러 개, list는 next 하나 (doubly면 prev 하나 더). singly linked list는 사실상 **자식이 한 개인 트리**다.

---

## 1. 백지 그리기 — 마스터 다이어그램 6장

### 1.1 ListNode 구조 (LeetCode 표준)

```
        ┌──────┬──────┐    ┌──────┬──────┐    ┌──────┬──────┐
 head ─▶│ val=1│ next ┼───▶│ val=2│ next ┼───▶│ val=3│ null │
        └──────┴──────┘    └──────┴──────┘    └──────┴──────┘
```

- val: 데이터
- next: 다음 노드 참조 (마지막은 null)
- doubly linked list라면 prev 필드 추가 (양방향)

### 1.2 In-place Reverse — 3-pointer Dance (가장 중요한 다이어그램)

뒤집기 한 스텝은 다음 4줄로 끝난다.

```java
ListNode next = cur.next;   // ① 다음 노드 저장 (잃지 않게)
cur.next = prev;            // ② 현재 노드의 화살표를 뒤로 돌림
prev = cur;                 // ③ prev 한 칸 전진
cur = next;                 // ④ cur 한 칸 전진
```

스텝별 시각화:

```
[초기 상태]
prev=null    cur=1 ──▶ 2 ──▶ 3 ──▶ null

[Step 1]   next=2 저장 → cur(1).next=prev(null) → prev=1, cur=2
prev ──▶ 1     cur=2 ──▶ 3 ──▶ null
         │
         null

[Step 2]   next=3 저장 → cur(2).next=prev(1) → prev=2, cur=3
              prev ──▶ 2 ──▶ 1 ──▶ null     cur=3 ──▶ null

[Step 3]   next=null 저장 → cur(3).next=prev(2) → prev=3, cur=null
              prev ──▶ 3 ──▶ 2 ──▶ 1 ──▶ null     cur=null

[종료] cur==null → return prev (=3, 새 head)
```

핵심: **next를 먼저 저장하지 않으면 cur.next=prev 순간 다음 노드를 영원히 잃는다.** 이 한 줄 누락이 코딩 테스트 가장 흔한 실수.

### 1.3 Fast/Slow Pointer — 중간 찾기

```
       1 ──▶ 2 ──▶ 3 ──▶ 4 ──▶ 5 ──▶ null
       ↑                ↑
      slow            fast (2칸씩)

slow=1, fast=1
slow=2, fast=3
slow=3, fast=5     ← fast.next==null, 종료
return slow (=3, 중간)

[짝수 길이] 1 ──▶ 2 ──▶ 3 ──▶ 4 ──▶ null
slow=1, fast=1
slow=2, fast=3
slow=3, fast=null  ← 종료
return slow (=3, 중간 두 개 중 뒤쪽)
```

루프 조건: `while (fast != null && fast.next != null)` — 짝수/홀수 모두 안전.

### 1.4 Floyd's Cycle Detection — Tortoise & Hare

```
       1 ──▶ 2 ──▶ 3 ──▶ 4 ──▶ 5
                    ▲                │
                    └────────────────┘
                       (cycle)

slow 1칸, fast 2칸. cycle이 있으면 언젠가 fast가 slow를 따라잡는다.
        - cycle 내부에서 fast가 slow보다 매 스텝마다 1칸씩 좁힌다.
        - cycle 길이가 L이면 최대 L 스텝 내 만남.
cycle 없으면 fast가 먼저 null 도달 → return false.
```

**왜 2배속인가?** 1배속(같은 속도)이면 영원히 못 만남. 3배속도 OK지만 수학이 복잡. 2배속이 최적.

### 1.5 Cycle 시작점 찾기 (Floyd Phase 2) — 수학 증명

```
   head ──── L ────▶ cycle 시작점 P
                          │
                          ▼
                    ┌─────────────┐
                    │             │
                  meeting M       │
                    │             │
                    └─── C-(M-P) ─┘  (cycle 길이 C)
```

만남까지 slow가 간 거리 = `L + d` (d = cycle 진입 후 거리)
만남까지 fast가 간 거리 = `L + d + nC` (n은 cycle 바퀴 수)
fast = 2 × slow → `L + d + nC = 2(L + d)` → `L = nC - d`

즉, **만남 지점에서 다시 1배속으로 가고, head에서도 1배속으로 가면 cycle 시작점에서 만난다.**

```java
slow = head;
while (slow != fast) { slow = slow.next; fast = fast.next; }
return slow;  // cycle 시작점
```

이 증명은 면접 꼬리질문 단골. 외우지 말고 그려서 유도하라.

### 1.6 Dummy (Sentinel) Head 트릭

```
[Without dummy]
   head ──▶ 1 ──▶ 2 ──▶ 3
   head 삭제? → head = head.next   (특수 케이스 분기 필요)

[With dummy]
   dummy ──▶ 1 ──▶ 2 ──▶ 3
   1 삭제? → dummy.next = dummy.next.next   (일반 케이스로 통합)
   return dummy.next
```

dummy head가 있으면 **"첫 노드 삭제/삽입" 분기가 사라진다**. 모든 노드에 prev가 존재하기 때문이다. Merge, Remove Nth, Reverse Between, Partition List — 거의 모든 변형에서 쓰인다.

### 1.7 K-Group Reverse 한 그림

```
[k=2]
   dummy ──▶ 1 ──▶ 2 ──▶ 3 ──▶ 4 ──▶ 5

[1차 그룹 reverse]
   dummy ──▶ 2 ──▶ 1 ──▶ 3 ──▶ 4 ──▶ 5
                     ↑
              groupPrev (다음 그룹 reverse 시작점)

[2차 그룹 reverse]
   dummy ──▶ 2 ──▶ 1 ──▶ 4 ──▶ 3 ──▶ 5
                                        ↑
                                     남은 노드 < k → 그대로
```

각 그룹은 sub-reverse, 그룹 간 연결은 `groupPrev.next` 갱신으로 이음.

---

## 2. 직관과 정의

### 2.1 한 줄 비유

> **배열 = 아파트 호수 (인덱스로 랜덤 액세스)**
> **Linked List = 보물찾기 쪽지 (다음 위치 종이로만 알 수 있음)**

### 2.2 정확한 정의

- **Singly Linked List**: 각 노드가 next 하나만 가짐. 역방향 순회 불가 (또는 O(n) 비용).
- **Doubly Linked List**: prev + next. 양방향 O(1) 순회. JDK `LinkedList`, `LinkedHashMap` entry가 이 구조.
- **Circular Linked List**: 마지막 노드가 첫 노드로 연결. 큐/버퍼 구현에 사용.

### 2.3 LeetCode 표준 ListNode 정의 (이 챕터 모든 코드의 전제)

**Java:**
```java
public class ListNode {
    int val;
    ListNode next;
    ListNode() {}
    ListNode(int val) { this.val = val; }
    ListNode(int val, ListNode next) { this.val = val; this.next = next; }
}
```

**Kotlin:**
```kotlin
class ListNode(var `val`: Int) {
    var next: ListNode? = null
}
```

> Kotlin의 `val`은 키워드이므로 백틱(`)으로 감싼다. LeetCode Kotlin 시그니처가 그렇다.

### 2.4 왜 Dummy Head Sentinel 패턴이 코드를 단순화하나

세 가지 이유.

1. **head가 바뀔 수 있는 연산에서 분기 제거**. 삭제·삽입·뒤집기 결과로 head가 다른 노드가 될 수 있는데, dummy.next로 반환하면 호출자 입장에서 항상 일관.
2. **null 체크 감소**. prev가 항상 존재하므로 `if (prev == null) head = ... else prev.next = ...` 같은 분기가 사라짐.
3. **for-loop 통일**. merge 같은 경우 "첫 노드를 어디에 붙일지" 결정이 평이해짐 (`tail.next = current; tail = tail.next`).

운영 마스터 관점: JDK `LinkedList`도 내부적으로 head/tail field를 가지며, 빈 리스트 = head=null=tail로 분기. 알고리즘 코드는 그 분기를 dummy로 통합한다. 둘 다 같은 문제를 다른 방식으로 푸는 것.

---

## 3. Java 템플릿 7종

### 3.1 Reverse Linked List (LeetCode 206)

```java
public ListNode reverseList(ListNode head) {
    ListNode prev = null;
    ListNode cur = head;
    while (cur != null) {
        ListNode next = cur.next;  // 다음 노드 저장
        cur.next = prev;           // 화살표 뒤집기
        prev = cur;                // prev 전진
        cur = next;                // cur 전진
    }
    return prev;  // 새 head
}
```

재귀 버전 (꼬리질문에 자주 나옴):

```java
public ListNode reverseListRecursive(ListNode head) {
    if (head == null || head.next == null) return head;
    ListNode newHead = reverseListRecursive(head.next);
    head.next.next = head;
    head.next = null;
    return newHead;
}
```

재귀는 콜 스택 O(n), 반복은 O(1) 추가 공간. 면접관이 "둘 다 보여줘" 하면 둘 다 줘라.

### 3.2 Merge Two Sorted Lists (LeetCode 21)

```java
public ListNode mergeTwoLists(ListNode l1, ListNode l2) {
    ListNode dummy = new ListNode(0);
    ListNode tail = dummy;
    while (l1 != null && l2 != null) {
        if (l1.val <= l2.val) {
            tail.next = l1;
            l1 = l1.next;
        } else {
            tail.next = l2;
            l2 = l2.next;
        }
        tail = tail.next;
    }
    tail.next = (l1 != null) ? l1 : l2;  // 남은 꼬리 한 번에 붙임
    return dummy.next;
}
```

dummy head 없으면 "첫 노드가 l1인지 l2인지" 분기가 필요. dummy로 일반화.

### 3.3 Remove Nth Node From End (LeetCode 19)

```java
public ListNode removeNthFromEnd(ListNode head, int n) {
    ListNode dummy = new ListNode(0, head);
    ListNode fast = dummy;
    ListNode slow = dummy;
    // fast를 n+1 칸 먼저 보냄
    for (int i = 0; i <= n; i++) fast = fast.next;
    // fast가 null이 될 때까지 같이 전진 → slow는 삭제할 노드의 앞
    while (fast != null) { fast = fast.next; slow = slow.next; }
    slow.next = slow.next.next;
    return dummy.next;
}
```

dummy 안 쓰면 "head 자체를 삭제" 케이스 분기. dummy로 통합.

### 3.4 Fast/Slow — Middle of List (LeetCode 876)

```java
public ListNode middleNode(ListNode head) {
    ListNode slow = head, fast = head;
    while (fast != null && fast.next != null) {
        slow = slow.next;
        fast = fast.next.next;
    }
    return slow;  // 짝수 길이면 뒤쪽 중간, 홀수면 정확한 중간
}
```

### 3.5 Cycle Detection (LeetCode 141)

```java
public boolean hasCycle(ListNode head) {
    ListNode slow = head, fast = head;
    while (fast != null && fast.next != null) {
        slow = slow.next;
        fast = fast.next.next;
        if (slow == fast) return true;
    }
    return false;
}
```

해시셋 버전도 가능하지만 (O(n) 공간), Floyd는 **O(1) 공간**으로 같은 일을 해서 면접 정답.

### 3.6 Cycle Start (LeetCode 142)

```java
public ListNode detectCycle(ListNode head) {
    ListNode slow = head, fast = head;
    while (fast != null && fast.next != null) {
        slow = slow.next;
        fast = fast.next.next;
        if (slow == fast) {  // Phase 1: 만남
            ListNode p = head;
            while (p != slow) { p = p.next; slow = slow.next; }
            return p;  // Phase 2: cycle 시작점
        }
    }
    return null;
}
```

수학 증명은 1.5절 참고. 면접에서 "왜 작동하는지?" 물으면 그림으로 설명.

### 3.7 K-Group Reverse (LeetCode 25)

```java
public ListNode reverseKGroup(ListNode head, int k) {
    ListNode dummy = new ListNode(0, head);
    ListNode groupPrev = dummy;

    while (true) {
        ListNode kth = getKth(groupPrev, k);
        if (kth == null) break;  // 남은 노드 < k → 그대로 종료
        ListNode groupNext = kth.next;

        // 그룹 내부 reverse: groupPrev.next ~ kth
        ListNode prev = groupNext;
        ListNode cur = groupPrev.next;
        while (cur != groupNext) {
            ListNode next = cur.next;
            cur.next = prev;
            prev = cur;
            cur = next;
        }

        ListNode tmp = groupPrev.next;  // 이 그룹의 새 마지막
        groupPrev.next = kth;            // 이전 그룹과 연결
        groupPrev = tmp;
    }
    return dummy.next;
}

private ListNode getKth(ListNode node, int k) {
    while (node != null && k > 0) { node = node.next; k--; }
    return node;
}
```

K-group은 sub-reverse + 그룹 간 stitching의 합성. dummy head 없이는 첫 그룹의 head 갱신이 지옥이다.

---

## 4. Kotlin 템플릿 7종

Kotlin은 nullable 타입 (`ListNode?`)을 명시적으로 다뤄야 해서 처음엔 장황해 보이지만, 본질은 같다.

### 4.1 Reverse (LeetCode 206)

```kotlin
fun reverseList(head: ListNode?): ListNode? {
    var prev: ListNode? = null
    var cur = head
    while (cur != null) {
        val next = cur.next
        cur.next = prev
        prev = cur
        cur = next
    }
    return prev
}
```

### 4.2 Merge Two Sorted Lists

```kotlin
fun mergeTwoLists(l1: ListNode?, l2: ListNode?): ListNode? {
    val dummy = ListNode(0)
    var tail = dummy
    var a = l1
    var b = l2
    while (a != null && b != null) {
        if (a.`val` <= b.`val`) {
            tail.next = a
            a = a.next
        } else {
            tail.next = b
            b = b.next
        }
        tail = tail.next!!
    }
    tail.next = a ?: b
    return dummy.next
}
```

### 4.3 Remove Nth From End

```kotlin
fun removeNthFromEnd(head: ListNode?, n: Int): ListNode? {
    val dummy = ListNode(0).apply { next = head }
    var fast: ListNode? = dummy
    var slow: ListNode? = dummy
    repeat(n + 1) { fast = fast?.next }
    while (fast != null) { fast = fast?.next; slow = slow?.next }
    slow?.next = slow?.next?.next
    return dummy.next
}
```

### 4.4 Middle Node

```kotlin
fun middleNode(head: ListNode?): ListNode? {
    var slow = head
    var fast = head
    while (fast?.next != null) {
        slow = slow?.next
        fast = fast.next?.next
    }
    return slow
}
```

### 4.5 Cycle Detection

```kotlin
fun hasCycle(head: ListNode?): Boolean {
    var slow = head
    var fast = head
    while (fast?.next != null) {
        slow = slow?.next
        fast = fast.next?.next
        if (slow === fast) return true
    }
    return false
}
```

Kotlin의 `===`는 reference equality. `==`은 `equals()` 호출이라 ListNode가 equals override 안 했어도 안전하지만, 의도를 명확히 하려면 `===`가 정석.

### 4.6 Cycle Start

```kotlin
fun detectCycle(head: ListNode?): ListNode? {
    var slow = head
    var fast = head
    while (fast?.next != null) {
        slow = slow?.next
        fast = fast.next?.next
        if (slow === fast) {
            var p = head
            while (p !== slow) { p = p?.next; slow = slow?.next }
            return p
        }
    }
    return null
}
```

### 4.7 K-Group Reverse

```kotlin
fun reverseKGroup(head: ListNode?, k: Int): ListNode? {
    val dummy = ListNode(0).apply { next = head }
    var groupPrev: ListNode = dummy

    while (true) {
        val kth = getKth(groupPrev, k) ?: break
        val groupNext = kth.next

        var prev = groupNext
        var cur = groupPrev.next
        while (cur !== groupNext) {
            val next = cur?.next
            cur?.next = prev
            prev = cur
            cur = next
        }

        val tmp = groupPrev.next!!
        groupPrev.next = kth
        groupPrev = tmp
    }
    return dummy.next
}

private fun getKth(node: ListNode?, k: Int): ListNode? {
    var n: ListNode? = node
    var rem = k
    while (n != null && rem > 0) { n = n.next; rem-- }
    return n
}
```

---

## 5. 시간/공간 복잡도

| 연산 | 시간 | 공간 | 비고 |
|---|---|---|---|
| Reverse (iterative) | O(n) | **O(1)** | in-place, 3-pointer |
| Reverse (recursive) | O(n) | O(n) | 콜 스택 |
| Merge two sorted | O(n+m) | O(1) | dummy 1개 |
| Remove Nth from end | O(n) | O(1) | 한 패스 fast/slow |
| Middle | O(n) | O(1) | 한 패스 fast/slow |
| Cycle detection (Floyd) | O(n) | **O(1)** | 해시셋 대비 공간 우위 |
| Cycle detection (HashSet) | O(n) | O(n) | 단순하지만 공간 ↑ |
| Cycle start (Floyd) | O(n) | O(1) | Phase 1 + Phase 2 |
| K-Group reverse | O(n) | O(1) | 각 노드 한 번씩 |
| Palindrome | O(n) | O(1) | 반 뒤집기 in-place |
| Copy with random (weaving) | O(n) | O(1) | 추가 노드 weave |
| Copy with random (hashmap) | O(n) | O(n) | 원→복사 매핑 |

**핵심 명제**: 거의 모든 단일 패스 linked list 문제는 **O(n) 시간, O(1) 추가 공간**으로 풀린다 — in-place pointer 조작 덕분. 해시셋/스택을 쓰는 풀이는 보통 "더 간단한 풀이"고, 면접 정답은 in-place.

---

## 6. 대표 문제 풀이 (9개)

### 6.1 LeetCode 206 — Reverse Linked List

**요약**: singly linked list의 head가 주어진다. 뒤집어서 새 head를 반환하라.

**접근**: 3-pointer dance (prev / cur / next). 가장 기본이므로 반드시 외워라.

**Java**:
```java
public ListNode reverseList(ListNode head) {
    ListNode prev = null, cur = head;
    while (cur != null) {
        ListNode next = cur.next;
        cur.next = prev;
        prev = cur;
        cur = next;
    }
    return prev;
}
```

**Kotlin**:
```kotlin
fun reverseList(head: ListNode?): ListNode? {
    var prev: ListNode? = null
    var cur = head
    while (cur != null) {
        val next = cur.next
        cur.next = prev
        prev = cur
        cur = next
    }
    return prev
}
```

**복잡도**: O(n) / O(1)

**함정**: `next` 저장을 빼먹으면 `cur.next = prev` 순간 다음 노드를 잃는다. 빈 리스트 (`head==null`) 도 자연스럽게 처리됨 (loop 미진입, prev=null 반환).

---

### 6.2 LeetCode 21 — Merge Two Sorted Lists

**요약**: 정렬된 두 리스트를 병합해 정렬된 한 리스트로.

**접근**: dummy head + tail 포인터. 두 리스트 헤드 비교 → 작은 쪽을 tail에 잇기.

**Java**:
```java
public ListNode mergeTwoLists(ListNode l1, ListNode l2) {
    ListNode dummy = new ListNode(0), tail = dummy;
    while (l1 != null && l2 != null) {
        if (l1.val <= l2.val) { tail.next = l1; l1 = l1.next; }
        else                  { tail.next = l2; l2 = l2.next; }
        tail = tail.next;
    }
    tail.next = (l1 != null) ? l1 : l2;
    return dummy.next;
}
```

**Kotlin**:
```kotlin
fun mergeTwoLists(l1: ListNode?, l2: ListNode?): ListNode? {
    val dummy = ListNode(0)
    var tail = dummy
    var a = l1; var b = l2
    while (a != null && b != null) {
        if (a.`val` <= b.`val`) { tail.next = a; a = a.next }
        else                    { tail.next = b; b = b.next }
        tail = tail.next!!
    }
    tail.next = a ?: b
    return dummy.next
}
```

**복잡도**: O(n+m) / O(1)

**함정**:
- 등호 처리: `<=`로 두면 stable merge. `<`로 하면 동일 값일 때 l2가 앞에 와서 stable이 깨짐. 면접에서 "stable이 필요한가요?" 물어보면 가산점.
- 한쪽 다 소진된 후 남은 꼬리를 `tail.next`에 한 번에 붙이기 — 잊으면 절반만 병합됨.

**확장**: LeetCode 23 (Merge k Sorted Lists) → Heap 패턴과 결합. 챕터 05 참고.

---

### 6.3 LeetCode 141 — Linked List Cycle

**요약**: 리스트에 사이클이 있는지 판단.

**접근**: Floyd's tortoise & hare. slow 1칸, fast 2칸. 만나면 cycle, fast null 도달이면 no cycle.

**Java**:
```java
public boolean hasCycle(ListNode head) {
    ListNode slow = head, fast = head;
    while (fast != null && fast.next != null) {
        slow = slow.next;
        fast = fast.next.next;
        if (slow == fast) return true;
    }
    return false;
}
```

**Kotlin**:
```kotlin
fun hasCycle(head: ListNode?): Boolean {
    var slow = head; var fast = head
    while (fast?.next != null) {
        slow = slow?.next
        fast = fast.next?.next
        if (slow === fast) return true
    }
    return false
}
```

**복잡도**: O(n) / O(1)

**함정**:
- 루프 조건 `fast != null && fast.next != null` — fast가 2칸 가니까 둘 다 체크. 하나만 체크하면 NPE.
- "처음에 둘 다 head"로 시작하면 첫 iteration 전엔 같음 → loop 안에서 먼저 전진 후 비교. 반대로 하면 무조건 true.
- HashSet 풀이는 O(n) 공간이라 면접 차선책. Floyd가 정석.

---

### 6.4 LeetCode 142 — Linked List Cycle II (사이클 시작점)

**요약**: 사이클이 있으면 시작 노드 반환, 없으면 null.

**접근**: Floyd Phase 1 (만남) + Phase 2 (head와 만남 지점에서 동시에 1칸씩 전진 → cycle 시작점에서 만남).

**Java**:
```java
public ListNode detectCycle(ListNode head) {
    ListNode slow = head, fast = head;
    while (fast != null && fast.next != null) {
        slow = slow.next;
        fast = fast.next.next;
        if (slow == fast) {
            ListNode p = head;
            while (p != slow) { p = p.next; slow = slow.next; }
            return p;
        }
    }
    return null;
}
```

**Kotlin**:
```kotlin
fun detectCycle(head: ListNode?): ListNode? {
    var slow = head; var fast = head
    while (fast?.next != null) {
        slow = slow?.next
        fast = fast.next?.next
        if (slow === fast) {
            var p = head
            while (p !== slow) { p = p?.next; slow = slow?.next }
            return p
        }
    }
    return null
}
```

**복잡도**: O(n) / O(1)

**함정**: Phase 2를 시작할 때 slow를 head로 되돌리는 변형도 있다 (`slow = head; while(slow != fast) ...`). 위 코드는 p를 새로 만들어서 head로 두고 slow는 그대로 둠. 둘 다 정답.

**수학 증명**: 1.5절. 면접관이 "왜 작동하나?" 물으면 그림 + 수식.

---

### 6.5 LeetCode 19 — Remove Nth Node From End

**요약**: 뒤에서 N번째 노드를 제거.

**접근**: dummy head + fast/slow gap. fast를 n+1 칸 먼저 보내고 같이 전진 → fast null 시 slow는 삭제할 노드의 앞.

**Java**:
```java
public ListNode removeNthFromEnd(ListNode head, int n) {
    ListNode dummy = new ListNode(0, head);
    ListNode fast = dummy, slow = dummy;
    for (int i = 0; i <= n; i++) fast = fast.next;
    while (fast != null) { fast = fast.next; slow = slow.next; }
    slow.next = slow.next.next;
    return dummy.next;
}
```

**Kotlin**:
```kotlin
fun removeNthFromEnd(head: ListNode?, n: Int): ListNode? {
    val dummy = ListNode(0).apply { next = head }
    var fast: ListNode? = dummy
    var slow: ListNode? = dummy
    repeat(n + 1) { fast = fast?.next }
    while (fast != null) { fast = fast?.next; slow = slow?.next }
    slow?.next = slow?.next?.next
    return dummy.next
}
```

**복잡도**: O(n) / O(1) — **한 패스 O(n)**

**함정**:
- dummy 없이 하면 "head 자체 삭제" (`n == length`) 케이스 분기. dummy로 통합.
- gap을 `n` 칸이 아니라 `n+1` 칸 두는 이유: slow가 삭제 대상의 **앞** 노드여야 `slow.next = slow.next.next` 가능. dummy를 시작점으로 두면 자연스럽게 +1.
- 두 패스 풀이 (length 먼저 측정 후 length-n번째 삭제) 도 OK지만 면접 가산점은 한 패스.

---

### 6.6 LeetCode 92 — Reverse Linked List II (구간 뒤집기)

**요약**: 인덱스 m~n 구간만 뒤집기 (1-indexed).

**접근**: dummy head로 시작 → m-1번째 노드 `prev`까지 전진 → 그 다음 n-m+1개를 reverse → 양 끝 stitching.

**Java**:
```java
public ListNode reverseBetween(ListNode head, int left, int right) {
    if (head == null || left == right) return head;
    ListNode dummy = new ListNode(0, head);
    ListNode prev = dummy;
    for (int i = 1; i < left; i++) prev = prev.next;

    // prev는 left-1 위치. cur는 left 위치.
    ListNode cur = prev.next;
    // 표준 in-place reverse를 right - left 번 수행
    for (int i = 0; i < right - left; i++) {
        ListNode next = cur.next;
        cur.next = next.next;
        next.next = prev.next;
        prev.next = next;
    }
    return dummy.next;
}
```

위 구현은 "head insertion" 트릭. cur는 reverse 동안 계속 같은 노드를 가리키되, 매 iteration마다 cur 뒤의 next 노드를 prev 바로 뒤로 옮긴다.

**Kotlin**:
```kotlin
fun reverseBetween(head: ListNode?, left: Int, right: Int): ListNode? {
    if (head == null || left == right) return head
    val dummy = ListNode(0).apply { next = head }
    var prev: ListNode = dummy
    for (i in 1 until left) prev = prev.next!!

    val cur = prev.next!!
    for (i in 0 until right - left) {
        val next = cur.next!!
        cur.next = next.next
        next.next = prev.next
        prev.next = next
    }
    return dummy.next
}
```

**복잡도**: O(n) / O(1)

**함정**:
- `left == right` 엣지: 뒤집을 게 없으므로 그대로 반환.
- 1-indexed: `for (i=1; i<left; i++)` — `left-1`회 이동해 `prev`가 `left-1` 위치.
- cur 위치 헷갈림: head-insertion 패턴에서 cur는 reverse 후 그룹의 마지막이 됨 (앞으로 빠지는 노드가 아님).

---

### 6.7 LeetCode 234 — Palindrome Linked List

**요약**: 리스트가 회문인지 판단. (1→2→2→1 = true)

**접근**:
1. fast/slow로 중간 찾기
2. 후반부 in-place reverse
3. 전반부와 후반부 비교

**Java**:
```java
public boolean isPalindrome(ListNode head) {
    if (head == null || head.next == null) return true;

    // 1) middle
    ListNode slow = head, fast = head;
    while (fast.next != null && fast.next.next != null) {
        slow = slow.next;
        fast = fast.next.next;
    }
    // slow = 전반부의 마지막 (홀수면 정확한 중간 - 후반부 시작은 slow.next)

    // 2) reverse second half
    ListNode second = reverse(slow.next);
    slow.next = null;

    // 3) compare
    ListNode p1 = head, p2 = second;
    boolean ok = true;
    while (p2 != null) {
        if (p1.val != p2.val) { ok = false; break; }
        p1 = p1.next; p2 = p2.next;
    }
    // 원본 복구 원하면 reverse 다시 (선택)
    return ok;
}

private ListNode reverse(ListNode head) {
    ListNode prev = null, cur = head;
    while (cur != null) { ListNode n = cur.next; cur.next = prev; prev = cur; cur = n; }
    return prev;
}
```

**Kotlin**:
```kotlin
fun isPalindrome(head: ListNode?): Boolean {
    if (head?.next == null) return true
    var slow = head; var fast = head
    while (fast?.next?.next != null) { slow = slow?.next; fast = fast.next?.next }

    var second = reverse(slow?.next)
    slow?.next = null

    var p1 = head; var p2 = second
    while (p2 != null) {
        if (p1?.`val` != p2.`val`) return false
        p1 = p1.next; p2 = p2.next
    }
    return true
}

private fun reverse(head: ListNode?): ListNode? {
    var prev: ListNode? = null; var cur = head
    while (cur != null) { val n = cur.next; cur.next = prev; prev = cur; cur = n }
    return prev
}
```

**복잡도**: O(n) / O(1)

**함정**:
- "stack에 다 넣고 비교"는 O(n) 공간. in-place 풀이가 면접 정답.
- 홀수 길이: 중간 노드는 비교에서 제외 (후반부가 더 짧음). 위 코드는 `while (p2 != null)`로 자연스럽게 처리.
- 원본 보존 요구 시 마지막에 다시 reverse 해서 복구. 면접관이 "thread-safe 한가요?" 물으면 "in-place 수정이라 동시 호출 시 깨집니다" 가산점.

---

### 6.8 LeetCode 25 — Reverse Nodes in k-Group

**요약**: k개씩 묶어 뒤집기. 남은 노드 < k면 그대로.

**접근**: dummy head → 매 그룹마다 (1) k번째 노드 확인 (2) 그룹 내부 reverse (3) 양 끝 stitching.

**Java**:
```java
public ListNode reverseKGroup(ListNode head, int k) {
    ListNode dummy = new ListNode(0, head);
    ListNode groupPrev = dummy;

    while (true) {
        ListNode kth = getKth(groupPrev, k);
        if (kth == null) break;
        ListNode groupNext = kth.next;

        ListNode prev = groupNext, cur = groupPrev.next;
        while (cur != groupNext) {
            ListNode next = cur.next;
            cur.next = prev;
            prev = cur;
            cur = next;
        }

        ListNode tmp = groupPrev.next;
        groupPrev.next = kth;
        groupPrev = tmp;
    }
    return dummy.next;
}

private ListNode getKth(ListNode node, int k) {
    while (node != null && k > 0) { node = node.next; k--; }
    return node;
}
```

**Kotlin**: 4.7절 참고.

**복잡도**: O(n) / O(1)

**함정**:
- `getKth(groupPrev, k)` — groupPrev 자체를 0번째로 보고 k번 이동해서 k번째 노드. 헷갈리면 그림.
- 그룹 내부 reverse 시 종료 조건이 `cur != groupNext` (== null이 아님!). 다음 그룹 첫 노드를 만나면 멈춰야 함.
- 재귀 풀이도 가능 (k개씩 떼어내고 재귀 호출). 콜 스택 O(n/k).

---

### 6.9 LeetCode 138 — Copy List with Random Pointer (advanced)

**요약**: 각 노드에 random 포인터가 추가로 있는 리스트의 deep copy.

```
   ┌──────┬──────┬────────┐
   │ val  │ next │ random │ → 다음 노드
   └──────┴──────┴────────┘
                    │
                    └─▶ 리스트 내 임의 노드 (또는 null)
```

**접근 1 (HashMap O(n) 공간)**: 원본 노드 → 복사 노드 매핑 해시맵. 두 패스 (1: 복사 노드 생성, 2: next/random 연결).

**접근 2 (Weaving O(1) 추가 공간)**: 각 원본 노드 뒤에 복사 노드를 끼워넣고 → random 연결 → 분리. 면접 고급 풀이.

**Java (Weaving)**:
```java
public Node copyRandomList(Node head) {
    if (head == null) return null;

    // 1) 원본 뒤에 복사 weave: A → A' → B → B' → ...
    Node cur = head;
    while (cur != null) {
        Node copy = new Node(cur.val);
        copy.next = cur.next;
        cur.next = copy;
        cur = copy.next;
    }

    // 2) random 설정: A'.random = A.random.next (A.random의 복사본)
    cur = head;
    while (cur != null) {
        if (cur.random != null) cur.next.random = cur.random.next;
        cur = cur.next.next;
    }

    // 3) 분리: 원본 복구 + 복사 리스트 추출
    Node dummy = new Node(0);
    Node copyTail = dummy;
    cur = head;
    while (cur != null) {
        copyTail.next = cur.next;
        copyTail = copyTail.next;
        cur.next = cur.next.next;  // 원본 복구
        cur = cur.next;
    }
    return dummy.next;
}
```

**Kotlin (HashMap, 간결 버전)**:
```kotlin
fun copyRandomList(head: Node?): Node? {
    if (head == null) return null
    val map = HashMap<Node, Node>()
    var cur: Node? = head
    while (cur != null) { map[cur] = Node(cur.`val`); cur = cur.next }
    cur = head
    while (cur != null) {
        map[cur]!!.next = map[cur.next]
        map[cur]!!.random = map[cur.random]
        cur = cur.next
    }
    return map[head]
}
```

**복잡도**:
- HashMap: O(n) / O(n)
- Weaving: O(n) / **O(1)** (출력 노드 제외)

**함정**:
- random이 null인 경우 처리. HashMap 풀이는 `map[null] = null` 가짜 매핑으로 단순화 가능.
- Weaving 풀이의 3단계 분리에서 원본을 복구하지 않으면 입력이 망가짐 — 면접관이 "원본 보존" 명시하면 가산점.
- 면접에서는 보통 둘 다 설명하고 trade-off 말하는 게 정답: HashMap은 간결하지만 공간 O(n), Weaving은 in-place지만 코드가 길다.

---

## 7. 함정·엣지케이스 체크리스트

면접에서 코드 다 쓰고 나서 **이 리스트를 소리내어 점검**하면 가산점.

### 7.1 null 체크

| 케이스 | 대응 |
|---|---|
| `head == null` | 빈 리스트 → 보통 그대로 반환 또는 null. 첫 줄에서 처리. |
| `head.next == null` | 단일 노드 → reverse, palindrome 등은 그대로 true/head. |
| 두 리스트 입력 (`l1`, `l2`) 모두 null | dummy head 패턴이면 자연스럽게 `dummy.next == null` 반환. |
| fast가 2칸 가는 도중 null | `while (fast != null && fast.next != null)` — 둘 다 체크. **단순히 `fast.next != null`만 체크하면 NPE**. |

### 7.2 Dummy Head 누락

- head가 바뀔 수 있는 모든 연산 (delete, insert at head, reverse, merge) 에 dummy 사용.
- "head를 안 바꿀 거 같은데" 했다가 엣지 케이스(첫 노드 삭제, 모두 삭제 등) 에서 깨짐.

### 7.3 prev/next 순서

In-place reverse에서 4줄 순서가 잘못되면 즉시 깨진다.

```java
// 올바른 순서
ListNode next = cur.next;   // ① 다음 저장
cur.next = prev;            // ② 뒤집기
prev = cur;                 // ③ prev 전진
cur = next;                 // ④ cur 전진

// 흔한 실수: ②와 ①을 바꿈
cur.next = prev;            // 다음 정보 잃음
ListNode next = cur.next;   // 이미 prev를 가리킴, 무한루프
```

### 7.4 Cycle 무한 루프

cycle 있는 리스트를 그냥 순회하면 무한루프. 진단:
- 디버그 시 출력 노드 수가 입력보다 많음 → cycle 의심
- `Set<ListNode> visited`로 안전 가드 (cycle 미상의 코드)

### 7.5 짝수/홀수 길이

| 길이 | fast/slow 종료 시 slow 위치 |
|---|---|
| 홀수 (1→2→3→4→5) | 정확한 중간 (3) |
| 짝수 (1→2→3→4) | 중간 두 개 중 뒤쪽 (3) |

palindrome 문제에서 짝수는 후반부 시작이 `slow`, 홀수는 `slow.next` 부터. 위 6.7 코드는 `slow = 전반부 마지막`으로 통일했음.

### 7.6 메모리 누수 (Java)

자바는 GC가 있지만 **순환 참조**는 reachable이 되면 영원히 살아남는다.
- `cur.next = prev` 후 `prev.prev = cur` (doubly) 같은 양방향이면 cycle reachable 동안 GC 안 함.
- LeetCode 문제에선 함수 끝나면 root 사라져 OK지만, 운영 코드에선 의도하지 않은 cycle 생성에 주의.

### 7.7 입력 mutate vs 새 리스트

- Reverse, Merge: 보통 입력 mutate OK (in-place).
- Copy with Random Pointer: 절대 mutate 금지 (deep copy 요구).
- 면접에서 "입력을 변경해도 되나요?" 한 마디 묻는 게 가산점.

---

## 8. 꼬리질문 트리

면접관이 정답 코드 받고 던지는 후속 질문들. 각각 30초 답변 준비.

### 8.1 "Doubly Linked List라면?"

- prev 필드 추가. 모든 연산이 O(1) backward 가능.
- Insert/Delete: prev/next 양쪽 갱신. 코드 줄 수 2배.
- 대표 사용처: **JDK `LinkedList`** (Deque 구현), **`LinkedHashMap`** (insertion/access order), **LRU cache**, **Redis LIST** (quicklist 내부).
- 단점: prev 포인터 64bit × 노드 수 추가 메모리. 모바일/임베디드에선 singly 선호.

### 8.2 "Skip List가 뭔가요?"

- multi-level linked list. 레벨 0은 전체, 레벨 1은 절반, 레벨 2는 1/4 … (확률적 1/2 승급).
- Search O(log n) 평균. Balanced BST의 alternative.
- 사용처: **Redis sorted set (ZSet)** 내부 (zskiplist), LevelDB MemTable, Java `ConcurrentSkipListMap`.
- 왜 BST 대신? lock-free 동시성 구현이 쉽다 (BST는 회전 시 광범위 락 필요).

### 8.3 "Linked vs Array — 메모리 캐시 친화도?"

- Array: 연속 메모리. CPU prefetcher가 다음 캐시 라인을 미리 가져옴. cache hit 율 높음.
- Linked List: 노드가 힙에 산재. 매 hop마다 cache miss 가능성. **L1 cache miss ≈ 10ns, RAM ≈ 100ns** → 10배 차이.
- 실측: 10만개 원소 순회 시 ArrayList가 LinkedList보다 3~10배 빠름 (`-XX:+PrintGCDetails`로 확인 가능).
- 결론: **"O(1) insert" 라는 이론적 장점은 cache miss로 상쇄됨**. JDK 후기 (8+) ArrayList가 거의 모든 상황의 default. LinkedList는 Deque로만 의미.

### 8.4 "LRU Cache 구현?"

`HashMap<Key, Node>` + `Doubly Linked List`:
- get: HashMap O(1) → Node → DLL에서 떼어내 head로 이동 O(1).
- put: 새 Node를 head에 삽입 O(1), 용량 초과면 tail 제거 O(1).

```
   head ◀──▶ A ◀──▶ B ◀──▶ C ◀──▶ tail   (sentinel head/tail 둘 다 dummy)
   HashMap: { keyA → Node A, keyB → Node B, ... }
```

JDK `LinkedHashMap`은 이미 이 구조. `removeEldestEntry()` override만 하면 LRU 완성.

```java
class LRUCache<K, V> extends LinkedHashMap<K, V> {
    private final int capacity;
    LRUCache(int capacity) { super(capacity, 0.75f, true); this.capacity = capacity; }
    @Override protected boolean removeEldestEntry(Map.Entry<K, V> eldest) {
        return size() > capacity;
    }
}
```

LeetCode 146 (LRU Cache) 문제는 이 구조를 **밑바닥부터** 만들 수 있는지 본다. HashMap + DLL을 직접 손으로 만드는 게 정답.

### 8.5 "Sentinel/Dummy 노드를 왜 두 개 (head + tail) 쓰는 경우가 있나요?"

DLL에서 head sentinel과 tail sentinel 둘 다 두면:
- 빈 리스트도 head.next == tail로 표현 (null 분기 0).
- 삽입/삭제 코드가 단일 분기로 통일.
- LRU 구현, Java `LinkedList` 내부 (LinkedList는 head/last를 null 허용으로 둠) 비교 시 알고리즘 코드는 sentinel 둘 두는 게 더 깔끔.

### 8.6 "Cycle이 있는 리스트에서 length 구하려면?"

Floyd로 만남 → 만남 지점에서 다시 1바퀴 돌아 cycle 길이 C → head에서 cycle 시작까지 길이 L → 총 length = L + C... 인데 사실 length가 정의 불가 (무한). 면접관이 의도한 답은 "총 unique 노드 수" 또는 "cycle 길이 따로, tail 길이 따로".

### 8.7 "Concurrent 환경에서 linked list?"

- `LinkedList`는 not thread-safe.
- `Collections.synchronizedList(new LinkedList<>())` — 모든 메서드에 lock. 성능 나쁨.
- `ConcurrentLinkedQueue` / `ConcurrentLinkedDeque` — Michael & Scott lock-free queue 알고리즘 (CAS 기반).
- 운영 패턴: producer-consumer엔 `LinkedBlockingQueue` (lock + condition), 고성능 ring buffer엔 Disruptor.

### 8.8 "Memory 절감하려면?"

- XOR linked list: `node.npx = prev XOR next` 하나로 양방향 저장. 메모리 절반. 단점: GC가 못 추적 (Java에선 불가, C/C++만).
- Unrolled linked list: 각 노드가 작은 배열 (e.g., 16개). cache locality + linked의 insertion 이점 절충.
- Redis LIST의 **ziplist/listpack** (작은 리스트는 연속 배열), **quicklist** (큰 리스트는 ziplist들의 doubly linked list).

---

## 9. 다른 패턴과의 연결

### 9.1 Stack을 Linked List로 구현

```java
class LinkedStack<T> {
    private Node<T> top;
    static class Node<T> { T val; Node<T> next; }
    public void push(T v) { Node<T> n = new Node<>(); n.val = v; n.next = top; top = n; }
    public T pop() { T v = top.val; top = top.next; return v; }
}
```

배열 stack은 resize 비용 (amortized O(1) but spike), linked stack은 매 push마다 노드 alloc (GC 압박). JDK `ArrayDeque`가 배열 기반 (faster), `LinkedList`는 doubly linked stack (slower but no resize spike). 챕터 04 참고.

### 9.2 Heap의 Array 구현 비교

Heap은 보통 array로 구현 (`parent = (i-1)/2`, `left = 2i+1`). Linked tree로도 가능하지만 cache locality 손해. PriorityQueue 내부도 `Object[] queue`. 챕터 05 참고.

→ **결론**: 같은 추상 자료구조도 underlying을 array로 할지 linked list로 할지에 따라 성능 특성이 다르다. 시니어 마스터는 "왜 이 자료구조가 이 구현을 선택했나" 를 본다.

### 9.3 LRU Cache (Hash + Doubly Linked List)

8.4절 참고. **Hash로 O(1) 조회 + DLL로 O(1) 순서 유지**. 이 조합은 면접 빈출이자 production 실무에서 가장 많이 쓰는 자료구조 합성 예시.

- Java `LinkedHashMap` (access-order mode)
- Caffeine cache (TinyLFU + LRU)
- Redis (maxmemory-policy=allkeys-lru)

### 9.4 Tree와의 관계

Singly linked list = 자식이 한 개인 트리. Tree DFS 순회를 linked list reverse처럼 in-place로 할 수도 있음 (Morris traversal, 챕터 14 참고).

### 9.5 Graph와의 관계

인접 리스트 그래프 표현 = `List<LinkedList<Integer>>`. 각 정점의 이웃 목록이 linked list. 챕터 11 참고.

---

## 10. 운영 마스터 관점 — Production에서의 Linked List

### 10.1 JDK `LinkedList`

```
LinkedList<E> implements List<E>, Deque<E>
  ├── doubly linked list
  ├── head/tail field (sentinel 없음, null 허용)
  └── size 필드 캐싱 (size() O(1))
```

언제 쓰나?
- **거의 안 씀**. 대부분 `ArrayList`가 빠르고 메모리 효율적.
- 예외: 빈번한 첫/끝 삽입+삭제 (Deque로). 이마저도 `ArrayDeque`가 더 빠름.

면접 잘 나오는 질문: "ArrayList vs LinkedList 언제 LinkedList 쓰는가?" → 솔직한 답은 "거의 없다, ArrayDeque/ArrayList로 대체".

### 10.2 `LinkedHashMap` 내부

```
LinkedHashMap.Entry<K,V> extends HashMap.Node<K,V> {
    Entry<K,V> before, after;  // doubly linked across all entries
}
```

HashMap.Node가 doubly linked list로 추가 연결됨. insertion order or access order 유지. LRU 구현의 핵심.

운영 시나리오: 캐시 만들 때 Map을 LinkedHashMap으로 바꾸고 access-order + removeEldestEntry → 무료 LRU. 외부 라이브러리 없이.

### 10.3 Redis LIST

Redis 3.2+ 부터 `quicklist` 사용:
- 외부: doubly linked list of nodes
- 각 노드: ziplist/listpack (작은 연속 배열, 압축 형식)
- 양쪽 끝 push/pop O(1), 중간 LINSERT/LSET은 O(n)

왜 이 구조? 순수 linked list는 메모리 오버헤드 (포인터) + cache miss. 순수 array는 중간 삽입 O(n). 절충: 작은 청크를 array로, 청크 간을 linked로.

실무 사용: 작업 큐 (LPUSH/BRPOP), 최신 N개 로그 (LPUSH + LTRIM), pub-sub 큐.

### 10.4 Linux 커널 `list.h`

`struct list_head { struct list_head *next, *prev; };` — circular doubly linked list. 모든 커널 자료구조 (process list, file list, ...)가 이걸 임베드. `container_of` 매크로로 owning struct 역추적.

C 환경의 끝판왕 linked list 패턴. Java 개발자도 한 번 보면 "왜 sentinel + circular이 가장 깔끔한가"를 이해.

### 10.5 Disruptor — Linked Queue를 버리는 이유

LMAX Disruptor (고성능 메시지 처리)는 일부러 **ring buffer** (array)로 만들었음. 이유:
- Linked queue의 노드 alloc → GC pressure
- Cache miss → CPU 효율 저하
- False sharing → 멀티코어 경합

→ 결론: 초고성능 환경에선 linked 자료구조를 array로 대체. "Linked List는 만능"이 아니다.

---

## 11. 마무리 — 백지 마스터 체크리스트

이 챕터를 마스터했다면 백지에서 다음을 줄줄 풀어낼 수 있어야 한다.

- [ ] ListNode 정의를 Java/Kotlin 양쪽으로 즉시 쓸 수 있다
- [ ] 3-pointer reverse 4줄을 prev/cur/next 명명까지 정확히 쓴다
- [ ] dummy head sentinel 트릭이 왜 head 변경 분기를 없애는지 1분 안에 설명한다
- [ ] fast/slow pointer로 중간/사이클/뒤에서 K번째를 즉시 코딩한다
- [ ] Floyd cycle detection이 왜 작동하는지 만남 거리 수식으로 증명한다
- [ ] K-group reverse를 dummy + groupPrev + getKth로 짠다
- [ ] Palindrome을 중간 분할 + reverse + 비교로 O(1) 공간에 푼다
- [ ] Copy with Random Pointer를 HashMap 풀이와 Weaving 풀이 둘 다 짠다
- [ ] LRU Cache를 HashMap + DLL로 밑바닥부터 짠다
- [ ] JDK `LinkedList` vs `ArrayList` 언제 뭘 쓰는지, `LinkedHashMap`이 LRU 구현의 핵심인 이유, Redis quicklist가 왜 array+linked 절충인지 설명한다

여기까지 되면 한국 라이브 코딩 테스트에서 Linked List 문제는 **30초 패턴 분류 + 5분 정답 코드 + 10분 엣지 케이스**로 끝낼 수 있다. 다음 챕터는 **07 Binary Search** — 정렬된 배열에서 답을 좁히는 패턴, 그리고 "답을 이분 탐색 (parametric)" 같은 고난도 변형을 다룬다.
