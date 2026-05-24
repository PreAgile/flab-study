# 14. Tree (트리) — 이진 트리 / BST / LCA / 균형 트리 / 트리 DP

> "트리는 순회만 하면 되는 거 아냐?"는 입문자. 마스터는 트리를 보면 **재귀적 자기 닮음(self-similar)** 을 떠올리고, BST면 `inorder = 정렬`을 즉시 잇고, "공통 조상"이 나오면 LCA를, "균형 여부"가 나오면 부모로 두 가지(높이 + flag)를 동시에 올려보내는 트리 DP를 본다. 그리고 production으로 점프 — 파일시스템 inode 트리, DOM, Spring `ApplicationContext` BeanFactory 트리, DB B+Tree 인덱스, JVM heap의 GC root 그래프, Kafka consumer group의 rebalance 트리, Kubernetes resource owner reference 트리까지 전부 같은 재귀 구조다.
>
> 트리를 마스터한다 = "자식 결과로 부모 결과를 만든다(post-order DP)"를 모든 문제에서 본능적으로 본다. 이 챕터는 옵션·문법 외우기 대신 **재귀 정의 → 4순회 → BST 성질 → LCA → 트리 DP → 직렬화** 본질만 다룬다.

---

## 0. 목차

0. 인지 신호 — 이 문제는 Tree 패턴인가?
1. 백지 그리기 — 4가지 순회 + BST + LCA + 재구성
2. 직관과 정의 — 트리, 이진 트리, BST, 균형 BST, 트리 DP
3. Java 템플릿 — TreeNode 정의 + 순회 + BST + LCA + 직렬화 + DP
4. Kotlin 템플릿 — 동일 변형
5. 시간/공간 복잡도 — 왜 O(n)/O(h)인가
6. 대표 문제 (10제) — LeetCode 104/226/110/98/235/236/102/105/297/230
7. 함정·엣지케이스 — null, BST 범위 전파, 직렬화 구분자, 좌우 swap
8. 꼬리질문 트리 — RB vs AVL, Trie, Segment Tree, Fenwick, B-Tree, n-ary
9. 다른 패턴과의 연결 — DFS/BFS/Heap/Trie/Graph

---

## 0. 인지 신호 — 이 문제는 Tree 패턴인가?

문제 설명에서 다음 단서가 보이면 **Tree 패턴**이다. 30초 안에 분류하라.

| 신호 | 예시 문구 | 즉시 떠올릴 것 |
|---|---|---|
| **TreeNode 입력** | "Given the root of a binary tree" | 재귀 함수 `dfs(node)` 시그니처 |
| **순회 요구** | "in-order", "level-order", "left/right child" | pre/in/post/level 4종 중 하나 |
| **BST 성질** | "binary search tree", "정렬된 트리" | inorder = 정렬, range로 validate |
| **공통 조상** | "Lowest Common Ancestor", "lowest node that has both p, q" | LCA — BST면 값 비교, 일반 트리면 분기점 찾기 |
| **균형 여부** | "balanced", "height-balanced", "AVL" | post-order에서 높이 + flag 동시 반환 |
| **직렬화/역직렬화** | "serialize/deserialize", "encode/decode" | preorder + null marker (`#`) |
| **트리 DP** | "max path sum", "longest path", "diameter", "rob houses on tree" | 자식 결과로 부모 결과 만들기 (post-order) |
| **재구성** | "construct from preorder and inorder" | preorder[0] = root, inorder에서 좌·우 분할 |
| **트리의 부모/자식** | "각 노드의 부모를 찾으라" | 루트에서 BFS/DFS로 부모 매핑 |
| **k번째 작은/큰 값** | "kth smallest in BST" | inorder 순회 + counter |

**반대로 트리가 아닌 경우** — 그래프(사이클 가능), 일반 배열, 문자열, 수학. 트리는 **사이클이 없고 노드 N개에 간선 N-1개인 연결 그래프**. 이 정의에서 "방문 표시(visited) 배열이 필요 없다"가 따라온다(부모만 빼면 됨).

---

## 1. 백지 그리기

### 1.1 한 트리, 네 가지 순회

같은 트리를 두고 방문 순서만 바꾼 게 4가지 순회. 백지에서 그릴 때 **이 트리 하나를 외워두면** 모든 순회 문제를 검증할 수 있다.

```
            1
          /   \
         2     3
        / \   / \
       4   5 6   7
```

| 순회 | 규칙 | 방문 순서 | 직관 |
|---|---|---|---|
| **pre-order** | 자기 → 좌 → 우 | 1 2 4 5 3 6 7 | "위에서부터 복사(serialize에 자연)" |
| **in-order** | 좌 → 자기 → 우 | 4 2 5 1 6 3 7 | "BST면 자동 정렬" |
| **post-order** | 좌 → 우 → 자기 | 4 5 2 6 7 3 1 | "자식 다 끝난 뒤 부모(트리 DP의 본질, 삭제 순서)" |
| **level-order** | 위에서 아래로, 한 줄씩 | 1 2 3 4 5 6 7 | "BFS, 최단 거리" |

```
pre-order  방문 시점         in-order 방문 시점          post-order 방문 시점
                                                            
     [1]                          1                              7
    /   \                       /   \                          /   \
   [2]   [3]                  [2]   [3]                      [3]   [7]
  / \   / \                  / \   / \                      / \   / \
 [3][4][5][6]               4   5 6   7                    1  2  4  5
                            ↑   ↑ ↑   ↑                    ↑  ↑  ↑  ↑
   ↑ 진입 시 record       inorder는 좌 끝 → 자신 → 우    leaf부터 거꾸로 올라옴
```

(괄호 안 숫자는 "방문 순번". 동일 그래프 위에 다른 시퀀스가 얹힌다.)

**기억법**:
- "pre/in/post"는 **자기 자신을 언제 record하는가**를 가리킨다 (좌·우는 항상 좌 먼저 우 나중).
- pre-order로 직렬화하면 root가 가장 먼저 나와 복원이 쉽다(LC 297).
- in-order BST = 정렬된 수열 (LC 98, 230).
- post-order는 자식 결과가 다 준비된 뒤 부모를 본다 → **트리 DP의 본질**.
- level-order는 큐 기반 BFS → 최단 거리·층별 합·우측 view.

### 1.2 BST(Binary Search Tree)의 성질

```
                    [8]
                   /   \
                 [3]    [10]
                / \       \
              [1] [6]     [14]
                  / \     /
                [4] [7] [13]

      ∀ node:  left subtree 모든 값 < node < right subtree 모든 값
                    (strict — 중복 허용 시 ≤ 로 정의 선택)
```

이 단 하나의 성질에서 다음이 따라온다.

1. **inorder 순회 = 정렬된 수열** → 1 3 4 6 7 8 10 13 14.
2. **검색 = O(h)** — 루트에서 값 비교로 좌·우 분기.
3. **lower_bound / upper_bound** — Java `TreeMap.ceilingKey/floorKey`.
4. **k번째 작은 값** — inorder 진행 중 counter 감소(LC 230).
5. **LCA** — 두 값이 동시에 root보다 작으면 좌, 크면 우, 그 외(끼이거나 같음)는 root가 LCA(LC 235).

**왜 균형이 중요한가** — sorted input을 그대로 insert하면 트리가 **linked list**가 되어 h = n, get/put O(n). 그래서 AVL / Red-Black / B-Tree가 등장.

### 1.3 LCA — BST vs 일반 트리

```
[BST LCA — O(h)]                         [Binary Tree LCA — O(n)]

         [6]                                      [3]
        /   \                                    /   \
      [2]   [8]    p=2, q=4                   [5]   [1]    p=5, q=4
      / \   / \                               / \   / \
    [0] [4][7][9]                           [6][2][0][8]
        / \                                    / \
      [3] [5]                                [7] [4]

  while node:                              dfs(node):
    if p < node < q: return node             if node == null: return null
    if p == node or q == node: return node   if node == p or node == q: return node
    if node > p and node > q:                left  = dfs(node.left)
        node = node.left                     right = dfs(node.right)
    else:                                    if left and right: return node
        node = node.right                    return left ?: right
```

**핵심 차이** — BST는 "값"으로 좌·우 결정 가능, 일반 트리는 **두 후보를 부모로 끌어올리며 합쳐지는 지점**을 본다. 일반 트리 LCA의 재귀 구조는 트리 DP의 정수 — 자식에서 결과가 올라오고, 부모가 결합한다.

### 1.4 트리 재구성 — preorder + inorder

```
preorder = [1, 2, 4, 5, 3, 6, 7]     ← root = preorder[0]
inorder  = [4, 2, 5, 1, 6, 3, 7]
            └─left subtree─┘ root └─right─┘
             4, 2, 5         1     6, 3, 7

재귀:
  build(preStart, preEnd, inStart, inEnd)
    root = preorder[preStart]
    mid = inorder에서 root 위치
    leftSize = mid - inStart
    left  = build(preStart+1,        preStart+leftSize, inStart, mid-1)
    right = build(preStart+leftSize+1, preEnd,           mid+1,   inEnd)
```

**최적화**: inorder의 값→index를 `HashMap`으로 전처리 → 매번 선형 탐색 제거 → O(n) (LC 105).

### 1.5 Morris 순회 — O(1) 공간으로 inorder

재귀/스택 없이 inorder를 도는 마법. 자기 subtree의 **rightmost predecessor**의 right pointer를 잠시 자기 자신으로 빌려 쓴 뒤 복원한다.

```
    [1]                       [1]                       [1]
   /   \      threading      /   \     traverse        /   \
  [2]   [3]    →→→→→→→     [2]   [3]   →→→→→→→     [2]   [3]
  / \             rightmost   / \  ─┐                 / \
[4] [5]           of left =  [4][5]│                [4] [5]
                  predecessor  └───┘  back to root
                  next = self
```

면접에서 묻는 빈도는 낮지만 **"O(1) 공간으로 inorder 가능?"** 꼬리질문이 들어오면 "Morris traversal — predecessor의 right로 thread"라고 한 줄 답할 수 있어야 마스터.

### 1.6 트리 DP의 본질 한 그림

```
              dp(root)
             /        \
        dp(left)    dp(right)
        /     \     /     \
      ...    ...  ...    ...

   post-order:
     leaf부터 dp 계산
     부모는 좌·우 dp 결과를 결합
     return 값을 "한 노드에서 위로 올라가는 것"과
            "자기에서 멈추고 갱신되는 것" 두 가지로 분리

  예) Diameter:
     dp(node) = max depth from node going down  ← return up
     answer  = max(answer, dp.left + dp.right)  ← 자기서 멈춤
```

이 구조 — **return 값과 전역 갱신값을 분리** — 가 LC 543(diameter), 124(max path sum), 110(balanced), 337(rob III), 968(camera) 전부에 적용된다.

---

## 2. 직관과 정의

### 2.1 트리의 수학적 정의

**트리** = 사이클이 없는 연결 그래프(undirected, connected, acyclic). 노드 n개면 간선 n-1개. 임의 두 노드 사이 경로 유일.

**루트 트리(rooted tree)** = 특정 노드 하나를 root로 지정한 트리. 모든 다른 노드는 root로부터의 깊이(depth)가 정의되고, 직계 위 노드를 부모(parent), 아래 노드를 자식(child)이라 부른다. 코딩 테스트의 거의 모든 트리는 rooted tree.

**이진 트리(binary tree)** = 모든 노드의 자식이 최대 2개(left/right). 위치가 다르면 다른 트리 — `[1, 2, null]`과 `[1, null, 2]`는 다르다.

### 2.2 이진 트리 vs BST vs 균형 BST

| 자료구조 | 추가 제약 | search/insert/delete | 대표 구현 |
|---|---|---|---|
| **Binary Tree** | 없음 (좌·우만) | O(n) worst | LeetCode 입력의 디폴트 |
| **BST** | left < node < right | O(h) — 균형이면 O(log n), 편향되면 O(n) | C++ `std::map` 없음 (RB), naive BST |
| **AVL Tree** | BST + 좌·우 높이 차 ≤ 1 | O(log n) 보장 | 인메모리 인덱스, 일부 DB |
| **Red-Black Tree** | BST + 색 규칙으로 높이 ≤ 2 log(n+1) | O(log n) 보장 | Java `TreeMap`, Linux CFS, C++ `std::map`/`set` |
| **B-Tree / B+Tree** | 다차 + 균형 | O(log n) 디스크 친화 | DB 인덱스 (InnoDB, Postgres B-tree) |
| **Trie** | 키가 문자열, 노드가 문자 | O(L) (L = 키 길이) | autocomplete, IP routing, dict |
| **Segment Tree** | 완전 이진 트리 + 구간 집계 | O(log n) range query/update | competitive, 시계열 |
| **Fenwick (BIT)** | 1-indexed 배열을 트리처럼 | O(log n) prefix sum | competitive |
| **Heap** | 완전 이진 트리 + 부모 ≤ 자식(min) | O(log n) push/pop, O(1) peek | PriorityQueue, OS scheduler |

**AVL vs Red-Black**:
- AVL은 더 엄격하게 균형 → 검색 약간 빠르지만 회전 잦음 → **read-heavy**.
- RB는 느슨한 균형 → 회전 적음 → **write-heavy / 메모리 캐시 / OS 스케줄러**.
- Java `TreeMap`이 RB인 이유 — 범용 라이브러리는 write도 잦으니 회전 적은 RB가 안전.

### 2.3 재귀 정의 — 트리 모든 알고리즘의 뿌리

```
Tree = empty
     | Node(value, Tree left, Tree right)
```

이 한 줄의 sum type에서 모든 알고리즘이 나온다.

```java
// Maximum Depth — 한 줄 정의가 한 줄 코드
int depth(TreeNode n) {
    return n == null ? 0 : 1 + Math.max(depth(n.left), depth(n.right));
}
```

**Base case (empty)** + **recursive case (좌, 우, 자기)** — 모든 트리 함수는 이 구조다. 문제를 만나면 먼저 "이 노드에서 좌·우에서 무엇을 받고, 무엇을 위로 넘기는가?"를 묻는다.

### 2.4 트리 DP — "자식 결과로 부모 결과 만들기"

**post-order**가 트리 DP의 자연스러운 순서. 자식이 다 끝난 뒤에야 부모가 계산 가능하기 때문.

```
패턴 시그니처:
  dfs(node) -> 어떤 값(들)
    if node == null: return base
    L = dfs(node.left)
    R = dfs(node.right)
    global = update(global, L, R, node)   // 자기에서 끝나는 답
    return combine(L, R, node)            // 위로 올리는 답
```

이 두 가지 — **"위로 올릴 값"과 "여기서 갱신할 값"을 분리하는 것** — 이 LC 124 max path sum의 핵심 통찰이고, LC 543 diameter도 같은 구조다.

### 2.5 운영 마스터 관점 — 트리는 코딩 테스트 밖에서도 어디에나 있다

| 시스템 | 트리 구조 | 어떤 연산 |
|---|---|---|
| **Linux 파일시스템** | inode 트리 (`/` → 디렉터리 → 파일) | `find` = DFS, `du` = post-order sum |
| **DOM** | HTML 문서 트리 | `document.querySelector` = DFS, CSS rule cascade = DFS |
| **Spring `ApplicationContext`** | 부모 ↔ 자식 BeanFactory 트리 | `getBean` 못 찾으면 parent로 위임 (Composite) |
| **DB B+Tree 인덱스** | 다차 균형 트리, leaf만 데이터 | range scan = leaf chain, point lookup = root→leaf |
| **JVM GC root 그래프** | (사실은 그래프지만 mark phase는 트리처럼 traverse) | reachability = DFS from roots |
| **React Fiber 트리** | Virtual DOM의 fiber linked tree | reconciliation = pre-order, commit = post-order |
| **Kubernetes ownerReferences** | Deployment → ReplicaSet → Pod | cascading delete = post-order |
| **Git 객체** | commit → tree → blob | content-addressed Merkle tree |
| **Kafka topic partitions의 ISR rebalance** | controller가 broker 트리로 propagate | failover = subtree 재배정 |
| **Trie in routing tables** | longest prefix match | IP 라우터, autocomplete |

→ 코딩 테스트에서 트리를 마스터한다는 건 **production system 설계의 기본 어휘**를 얻는 것.

---

## 3. Java 템플릿

### 3.1 TreeNode 정의 (이 챕터 전체에서 한 번만 명시)

```java
public class TreeNode {
    int val;
    TreeNode left;
    TreeNode right;
    TreeNode() {}
    TreeNode(int val) { this.val = val; }
    TreeNode(int val, TreeNode left, TreeNode right) {
        this.val = val;
        this.left = left;
        this.right = right;
    }
}
```

(LeetCode 표준 시그니처. 입력이 인접 리스트로 들어오는 변형에서는 별도 변환 단계가 필요.)

### 3.2 네 가지 순회 — 재귀와 iterative 양쪽

#### Pre-order (재귀)

```java
List<Integer> preorder(TreeNode root) {
    List<Integer> out = new ArrayList<>();
    dfs(root, out);
    return out;
}
void dfs(TreeNode n, List<Integer> out) {
    if (n == null) return;
    out.add(n.val);          // 자기
    dfs(n.left, out);        // 좌
    dfs(n.right, out);       // 우
}
```

#### Pre-order (iterative — 스택 사용, 우→좌 push)

```java
List<Integer> preorderIter(TreeNode root) {
    List<Integer> out = new ArrayList<>();
    if (root == null) return out;
    Deque<TreeNode> stack = new ArrayDeque<>();
    stack.push(root);
    while (!stack.isEmpty()) {
        TreeNode n = stack.pop();
        out.add(n.val);
        if (n.right != null) stack.push(n.right);   // 우 먼저 push
        if (n.left  != null) stack.push(n.left);    // 좌가 위에 — 먼저 pop
    }
    return out;
}
```

#### In-order (iterative — 마스터 단골)

```java
List<Integer> inorderIter(TreeNode root) {
    List<Integer> out = new ArrayList<>();
    Deque<TreeNode> stack = new ArrayDeque<>();
    TreeNode cur = root;
    while (cur != null || !stack.isEmpty()) {
        while (cur != null) {           // 좌로 끝까지
            stack.push(cur);
            cur = cur.left;
        }
        cur = stack.pop();              // 가장 왼쪽
        out.add(cur.val);               // 방문
        cur = cur.right;                // 우 subtree로
    }
    return out;
}
```

#### Post-order (iterative — 두 스택 트릭)

```java
List<Integer> postorderIter(TreeNode root) {
    LinkedList<Integer> out = new LinkedList<>();   // addFirst
    if (root == null) return out;
    Deque<TreeNode> stack = new ArrayDeque<>();
    stack.push(root);
    while (!stack.isEmpty()) {
        TreeNode n = stack.pop();
        out.addFirst(n.val);                        // 거꾸로 쌓기 → 결과는 post-order
        if (n.left  != null) stack.push(n.left);
        if (n.right != null) stack.push(n.right);
    }
    return out;
}
```

(pre-order를 좌·우 뒤집어 만든 뒤 결과를 reverse — "modified pre-order"로 외우면 편하다.)

#### Level-order (BFS, 큐)

```java
List<List<Integer>> levelOrder(TreeNode root) {
    List<List<Integer>> out = new ArrayList<>();
    if (root == null) return out;
    Queue<TreeNode> q = new ArrayDeque<>();
    q.offer(root);
    while (!q.isEmpty()) {
        int size = q.size();                        // 이번 레벨 크기 snapshot
        List<Integer> level = new ArrayList<>(size);
        for (int i = 0; i < size; i++) {
            TreeNode n = q.poll();
            level.add(n.val);
            if (n.left  != null) q.offer(n.left);
            if (n.right != null) q.offer(n.right);
        }
        out.add(level);
    }
    return out;
}
```

**`size` snapshot이 핵심** — 한 레벨 끝났음을 큐 크기로 구분. (LC 102, 199, 515 전부 동일 패턴.)

### 3.3 BST 기본 — search / insert / validate

#### search (O(h))

```java
TreeNode searchBST(TreeNode root, int target) {
    while (root != null && root.val != target) {
        root = target < root.val ? root.left : root.right;
    }
    return root;
}
```

#### insert (재귀)

```java
TreeNode insertBST(TreeNode root, int v) {
    if (root == null) return new TreeNode(v);
    if (v < root.val) root.left  = insertBST(root.left,  v);
    else              root.right = insertBST(root.right, v);
    return root;
}
```

#### validate (범위 전파 — `> low && < high`)

```java
boolean isValidBST(TreeNode root) {
    return validate(root, null, null);   // null = ±∞
}
boolean validate(TreeNode n, Integer low, Integer high) {
    if (n == null) return true;
    if (low  != null && n.val <= low ) return false;
    if (high != null && n.val >= high) return false;
    return validate(n.left,  low,    n.val)
        && validate(n.right, n.val,  high);
}
```

**왜 부모만 비교하면 안 되나** — `[5, 1, 4, null, null, 3, 6]`은 4 < 5(좌)지만 4 안의 3은 5보다 작아야 하는데 좌서브트리 안의 모든 노드를 5보다 작게 강제해야 한다. 그래서 `low/high`를 **전파**한다.

### 3.4 LCA — BST와 일반 트리

#### LCA in BST (LC 235) — O(h)

```java
TreeNode lcaBST(TreeNode root, TreeNode p, TreeNode q) {
    while (root != null) {
        if (p.val < root.val && q.val < root.val) root = root.left;
        else if (p.val > root.val && q.val > root.val) root = root.right;
        else return root;                       // 끼이거나 같음
    }
    return null;
}
```

#### LCA in Binary Tree (LC 236) — O(n)

```java
TreeNode lca(TreeNode root, TreeNode p, TreeNode q) {
    if (root == null || root == p || root == q) return root;
    TreeNode L = lca(root.left,  p, q);
    TreeNode R = lca(root.right, p, q);
    if (L != null && R != null) return root;    // 좌·우에서 각각 발견 → 여기서 합쳐짐
    return L != null ? L : R;
}
```

### 3.5 직렬화 / 역직렬화 (LC 297) — preorder + null marker

```java
public class Codec {
    public String serialize(TreeNode root) {
        StringBuilder sb = new StringBuilder();
        ser(root, sb);
        return sb.toString();
    }
    void ser(TreeNode n, StringBuilder sb) {
        if (n == null) { sb.append("#,"); return; }
        sb.append(n.val).append(',');
        ser(n.left,  sb);
        ser(n.right, sb);
    }
    public TreeNode deserialize(String data) {
        Deque<String> q = new ArrayDeque<>(Arrays.asList(data.split(",")));
        return des(q);
    }
    TreeNode des(Deque<String> q) {
        String s = q.poll();
        if (s.equals("#")) return null;
        TreeNode n = new TreeNode(Integer.parseInt(s));
        n.left  = des(q);
        n.right = des(q);
        return n;
    }
}
```

**왜 preorder인가** — root가 먼저 나와 복원이 자연스럽다. inorder 단독으로는 복원 불가(좌·우 경계를 모름). null marker(`#`)가 필수 — 없으면 같은 inorder를 가진 두 트리를 구분 못 한다.

### 3.6 트리 DP 시그니처

```java
int answer;                              // 전역 갱신값

int dfs(TreeNode n) {
    if (n == null) return 0;
    int L = Math.max(0, dfs(n.left));    // 음수는 잘라냄 (문제에 따라)
    int R = Math.max(0, dfs(n.right));
    answer = Math.max(answer, L + R + n.val);  // 자기에서 멈춤
    return n.val + Math.max(L, R);             // 위로 올림 (한쪽만)
}
```

**한쪽만 올린다** — 부모 경로로 이어갈 때는 좌·우 둘 다 쓸 수 없다(트리는 사이클이 없어 한 노드를 두 번 못 거침). 자기에서 끝날 때만 좌+우.

---

## 4. Kotlin 템플릿

### 4.1 TreeNode (LeetCode Kotlin 표준)

```kotlin
class TreeNode(var `val`: Int) {
    var left:  TreeNode? = null
    var right: TreeNode? = null
}
```

(`val`이 Kotlin 예약어라 백틱. 면접에서 백틱 안 쓰려면 변수명을 `v`로 destructure하는 트릭도 있지만 LC 기본 시그니처를 따르는 게 안전하다.)

### 4.2 순회 — Kotlin 관용

```kotlin
fun preorder(root: TreeNode?): List<Int> {
    val out = mutableListOf<Int>()
    fun dfs(n: TreeNode?) {
        if (n == null) return
        out += n.`val`
        dfs(n.left); dfs(n.right)
    }
    dfs(root); return out
}

fun inorderIter(root: TreeNode?): List<Int> {
    val out = mutableListOf<Int>()
    val stack = ArrayDeque<TreeNode>()
    var cur = root
    while (cur != null || stack.isNotEmpty()) {
        while (cur != null) { stack.addLast(cur); cur = cur.left }
        cur = stack.removeLast()
        out += cur.`val`
        cur = cur.right
    }
    return out
}

fun levelOrder(root: TreeNode?): List<List<Int>> {
    val out = mutableListOf<MutableList<Int>>()
    if (root == null) return out
    val q: ArrayDeque<TreeNode> = ArrayDeque(); q.addLast(root)
    while (q.isNotEmpty()) {
        val size = q.size
        val level = ArrayList<Int>(size)
        repeat(size) {
            val n = q.removeFirst()
            level += n.`val`
            n.left ?.let { q.addLast(it) }
            n.right?.let { q.addLast(it) }
        }
        out += level
    }
    return out
}
```

### 4.3 BST validate — Kotlin

```kotlin
fun isValidBST(root: TreeNode?): Boolean {
    fun ok(n: TreeNode?, low: Long, high: Long): Boolean {
        if (n == null) return true
        if (n.`val` <= low || n.`val` >= high) return false
        return ok(n.left, low, n.`val`.toLong()) && ok(n.right, n.`val`.toLong(), high)
    }
    return ok(root, Long.MIN_VALUE, Long.MAX_VALUE)
}
```

(Long으로 ±∞ 표현 — `Integer.MIN_VALUE`가 노드 값일 수 있어 overflow 회피. Java에서도 같은 트릭 가능.)

### 4.4 LCA

```kotlin
fun lca(root: TreeNode?, p: TreeNode?, q: TreeNode?): TreeNode? {
    if (root == null || root === p || root === q) return root
    val L = lca(root.left,  p, q)
    val R = lca(root.right, p, q)
    return when {
        L != null && R != null -> root
        L != null              -> L
        else                   -> R
    }
}
```

### 4.5 직렬화

```kotlin
class Codec {
    fun serialize(root: TreeNode?): String = buildString {
        fun go(n: TreeNode?) {
            if (n == null) { append("#,"); return }
            append(n.`val`).append(',')
            go(n.left); go(n.right)
        }
        go(root)
    }
    fun deserialize(data: String): TreeNode? {
        val q: ArrayDeque<String> = ArrayDeque(data.split(','))
        fun go(): TreeNode? {
            val s = q.removeFirst()
            if (s == "#") return null
            return TreeNode(s.toInt()).apply {
                left  = go()
                right = go()
            }
        }
        return go()
    }
}
```

### 4.6 트리 DP

```kotlin
var answer = Int.MIN_VALUE
fun dfs(n: TreeNode?): Int {
    if (n == null) return 0
    val L = maxOf(0, dfs(n.left))
    val R = maxOf(0, dfs(n.right))
    answer = maxOf(answer, L + R + n.`val`)
    return n.`val` + maxOf(L, R)
}
```

---

## 5. 시간 / 공간 복잡도

| 연산 | 시간 | 공간 | 근거 |
|---|---|---|---|
| 모든 순회 (재귀) | O(n) | O(h) | 노드 한 번씩 방문, 스택은 깊이 h |
| 모든 순회 (iterative) | O(n) | O(h) | 명시적 스택/큐가 깊이만큼 |
| Morris inorder | O(n) | **O(1)** | thread 재사용, 각 간선 최대 2회 |
| BST search/insert/delete | O(h) | O(h) (재귀) | h = 균형 시 log n, 편향 시 n |
| AVL/RB search/insert/delete | O(log n) | O(log n) | 회전으로 균형 유지 |
| LCA BST | O(h) | O(1) | 반복문으로 한쪽씩 |
| LCA Binary Tree | O(n) | O(h) | 전부 방문해야 합쳐지는지 판정 |
| Serialize/Deserialize | O(n) | O(n) | 결과 문자열 + 스택 |
| Construct from pre+in (HashMap) | O(n) | O(n) | inorder index map |
| Construct from pre+in (naive) | O(n²) | O(h) | inorder에서 매번 선형 탐색 |
| Diameter / Max Path Sum | O(n) | O(h) | post-order 한 번 |

**h vs log n** — "트리 알고리즘은 O(log n)"이라고 답하면 절반만 맞다. **균형 트리에서만** O(log n)이고, naive BST는 worst O(n). 면접에서 정확히 "O(h), 균형이면 O(log n)"이라고 답하라.

**재귀 스택 오버플로우** — JVM 기본 스레드 스택 약 512KB ~ 1MB. 깊이 ~10⁴ 근처면 `StackOverflowError`. 큰 트리에서 안전하려면 iterative 또는 `-Xss` 증가 또는 명시적 스택.

---

## 6. 대표 문제

### 6.1 LeetCode 104 — Maximum Depth of Binary Tree

**요약** — 이진 트리의 최대 깊이 반환.

**접근** — 한 줄 재귀. "leaf의 깊이 1, 부모는 max(left, right) + 1". 트리 DP 입문.

```java
public int maxDepth(TreeNode root) {
    if (root == null) return 0;
    return 1 + Math.max(maxDepth(root.left), maxDepth(root.right));
}
```

```kotlin
fun maxDepth(root: TreeNode?): Int =
    if (root == null) 0 else 1 + maxOf(maxDepth(root.left), maxDepth(root.right))
```

**복잡도** — O(n) time, O(h) space.

**함정** — null 트리는 깊이 0(아니라 1로 잘못 답하기 쉽다). BFS로도 풀 수 있지만 재귀가 짧다.

---

### 6.2 LeetCode 226 — Invert Binary Tree

**요약** — 모든 노드의 좌·우 자식을 swap.

**접근** — post-order(자식을 invert한 뒤 자기 swap) 또는 pre-order(자기 swap 후 자식). 한 줄.

```java
public TreeNode invertTree(TreeNode root) {
    if (root == null) return null;
    TreeNode l = invertTree(root.left);
    TreeNode r = invertTree(root.right);
    root.left  = r;
    root.right = l;
    return root;
}
```

```kotlin
fun invertTree(root: TreeNode?): TreeNode? {
    if (root == null) return null
    val l = invertTree(root.left)
    val r = invertTree(root.right)
    root.left  = r
    root.right = l
    return root
}
```

**복잡도** — O(n) / O(h).

**함정** — 임시 변수 없이 `root.left = invertTree(root.right); root.right = invertTree(root.left)`로 쓰면 첫 줄에서 `root.left`가 덮여 두 번째 줄이 잘못된 subtree를 invert. **반드시 좌·우 결과를 먼저 받고** 나서 대입.

**Production 연결** — 좌우 swap이 의미 있는 경우는 거의 없지만, "트리 구조를 in-place로 변환"하는 일반 패턴(예: AST optimization, JSON path 정규화)은 자주 등장.

---

### 6.3 LeetCode 110 — Balanced Binary Tree

**요약** — 모든 노드에서 `|h(left) - h(right)| ≤ 1`인지 판별.

**접근 1 (Naive O(n log n))** — 매 노드에서 `height(left)`, `height(right)` 호출 → 같은 subtree 높이를 여러 번 계산.

**접근 2 (마스터 O(n))** — post-order에서 **높이와 unbalanced flag를 동시에 반환**. `-1`을 sentinel로.

```java
public boolean isBalanced(TreeNode root) {
    return height(root) != -1;
}
int height(TreeNode n) {
    if (n == null) return 0;
    int L = height(n.left);
    if (L == -1) return -1;
    int R = height(n.right);
    if (R == -1) return -1;
    if (Math.abs(L - R) > 1) return -1;
    return 1 + Math.max(L, R);
}
```

```kotlin
fun isBalanced(root: TreeNode?): Boolean = height(root) != -1
private fun height(n: TreeNode?): Int {
    if (n == null) return 0
    val L = height(n.left);  if (L == -1) return -1
    val R = height(n.right); if (R == -1) return -1
    if (kotlin.math.abs(L - R) > 1) return -1
    return 1 + maxOf(L, R)
}
```

**복잡도** — O(n) / O(h).

**함정** — naive 방식은 skew tree에서 O(n²). 면접에서 O(n) 풀이를 못 내면 감점. "sentinel 값으로 두 정보(높이 + 균형 여부)를 한 return에" 가 트리 DP 마스터 신호.

---

### 6.4 LeetCode 98 — Validate Binary Search Tree

**요약** — 주어진 이진 트리가 BST인지 판별.

**접근 1 (범위 전파, 위에서 아래로)** — `validate(n, low, high)`로 허용 범위를 좁혀가며 전파.

**접근 2 (inorder + 직전 값 추적)** — BST면 inorder가 strict ascending → 직전 값 ≥ 현재 값이면 false.

```java
// 접근 1
public boolean isValidBST(TreeNode root) {
    return validate(root, Long.MIN_VALUE, Long.MAX_VALUE);
}
boolean validate(TreeNode n, long low, long high) {
    if (n == null) return true;
    if (n.val <= low || n.val >= high) return false;
    return validate(n.left, low, n.val) && validate(n.right, n.val, high);
}

// 접근 2 (inorder)
long prev = Long.MIN_VALUE;
public boolean isValidBST2(TreeNode root) {
    if (root == null) return true;
    if (!isValidBST2(root.left)) return false;
    if (root.val <= prev) return false;
    prev = root.val;
    return isValidBST2(root.right);
}
```

```kotlin
fun isValidBST(root: TreeNode?): Boolean {
    fun ok(n: TreeNode?, low: Long, high: Long): Boolean {
        if (n == null) return true
        if (n.`val` <= low || n.`val` >= high) return false
        return ok(n.left, low, n.`val`.toLong()) && ok(n.right, n.`val`.toLong(), high)
    }
    return ok(root, Long.MIN_VALUE, Long.MAX_VALUE)
}
```

**복잡도** — O(n) / O(h).

**함정**:
- "부모와만 비교"하면 좌서브트리 안쪽이 부모를 넘어서는 경우를 못 잡음.
- `Integer.MIN/MAX_VALUE`를 노드 값으로 허용하므로 sentinel은 `Long` 또는 `Integer` boxing nullable.
- strict `<` — 중복 허용 X (LC 98 정의).

---

### 6.5 LeetCode 235 — Lowest Common Ancestor of a BST

**요약** — BST에서 두 노드 p, q의 LCA.

**접근** — root에서 시작, 두 값이 모두 root보다 작으면 좌, 모두 크면 우, **그 외에는 root가 LCA**. 끼이는 순간 = 분기점.

```java
public TreeNode lowestCommonAncestor(TreeNode root, TreeNode p, TreeNode q) {
    while (root != null) {
        if (p.val < root.val && q.val < root.val) root = root.left;
        else if (p.val > root.val && q.val > root.val) root = root.right;
        else return root;
    }
    return null;
}
```

```kotlin
fun lowestCommonAncestor(root: TreeNode?, p: TreeNode?, q: TreeNode?): TreeNode? {
    var cur = root
    val pv = p!!.`val`; val qv = q!!.`val`
    while (cur != null) {
        cur = when {
            pv < cur.`val` && qv < cur.`val` -> cur.left
            pv > cur.`val` && qv > cur.`val` -> cur.right
            else -> return cur
        }
    }
    return null
}
```

**복잡도** — O(h) / O(1).

**함정** — p나 q 자신이 LCA일 수 있다(LC 235 정의가 "노드는 자신의 후손"으로 본다). `≤`/`≥` 비교를 잘못하면 자기를 못 잡는다. `<`/`>`로 엄격히, 그 외 → return.

---

### 6.6 LeetCode 236 — Lowest Common Ancestor of a Binary Tree

**요약** — 일반 이진 트리에서 두 노드의 LCA.

**접근** — post-order. "내 좌서브트리에서 하나, 우서브트리에서 하나 발견 → 내가 LCA". 한쪽에만 발견되면 그 결과를 부모로 올린다.

```java
public TreeNode lowestCommonAncestor(TreeNode root, TreeNode p, TreeNode q) {
    if (root == null || root == p || root == q) return root;
    TreeNode L = lowestCommonAncestor(root.left,  p, q);
    TreeNode R = lowestCommonAncestor(root.right, p, q);
    if (L != null && R != null) return root;
    return L != null ? L : R;
}
```

```kotlin
fun lowestCommonAncestor(root: TreeNode?, p: TreeNode?, q: TreeNode?): TreeNode? {
    if (root == null || root === p || root === q) return root
    val L = lowestCommonAncestor(root.left,  p, q)
    val R = lowestCommonAncestor(root.right, p, q)
    return if (L != null && R != null) root else (L ?: R)
}
```

**복잡도** — O(n) / O(h).

**함정**:
- p, q가 트리에 반드시 존재한다는 가정(LC 236) — 없을 수 있는 변형은 "양쪽 발견 여부" 별도 추적.
- `root == p` 시 즉시 return — 자기가 LCA 가능.
- 부모 포인터가 있으면 두 노드의 path를 위로 거슬러 올라가다 만나는 점 — O(h) 가능. (Trees with parent pointer 변형)

**Production 연결** — Git의 `merge-base`(공통 조상 commit) = DAG 위에서의 LCA. Kubernetes ownerReferences 트리에서 "두 리소스의 공통 owner".

---

### 6.7 LeetCode 102 — Binary Tree Level Order Traversal

**요약** — 레벨별로 묶어 반환.

**접근** — BFS + `size` snapshot 패턴.

```java
public List<List<Integer>> levelOrder(TreeNode root) {
    List<List<Integer>> out = new ArrayList<>();
    if (root == null) return out;
    Queue<TreeNode> q = new ArrayDeque<>();
    q.offer(root);
    while (!q.isEmpty()) {
        int size = q.size();
        List<Integer> level = new ArrayList<>(size);
        for (int i = 0; i < size; i++) {
            TreeNode n = q.poll();
            level.add(n.val);
            if (n.left  != null) q.offer(n.left);
            if (n.right != null) q.offer(n.right);
        }
        out.add(level);
    }
    return out;
}
```

```kotlin
fun levelOrder(root: TreeNode?): List<List<Int>> {
    val out = mutableListOf<List<Int>>()
    if (root == null) return out
    val q = ArrayDeque<TreeNode>().apply { addLast(root) }
    while (q.isNotEmpty()) {
        val size = q.size
        val level = ArrayList<Int>(size)
        repeat(size) {
            val n = q.removeFirst()
            level += n.`val`
            n.left ?.let { q.addLast(it) }
            n.right?.let { q.addLast(it) }
        }
        out += level
    }
    return out
}
```

**복잡도** — O(n) / O(w), w = 최대 폭. 완전 이진 트리면 w ≈ n/2.

**함정** — 큐 size snapshot을 안 잡으면 같은 레벨에 push된 자식들이 섞여 잘못 grouping. 변형: 199번(right side view) → 각 레벨 마지막 원소만 추가.

---

### 6.8 LeetCode 105 — Construct Binary Tree from Preorder and Inorder

**요약** — preorder와 inorder 배열로부터 트리 복원.

**접근** — preorder[0] = root, inorder에서 root 위치 찾기 → 좌·우 길이 결정. inorder 값→index를 HashMap으로 전처리.

```java
public class Solution {
    Map<Integer, Integer> idx;
    int[] pre;
    int p = 0;

    public TreeNode buildTree(int[] preorder, int[] inorder) {
        pre = preorder;
        idx = new HashMap<>();
        for (int i = 0; i < inorder.length; i++) idx.put(inorder[i], i);
        return build(0, inorder.length - 1);
    }
    TreeNode build(int inL, int inR) {
        if (inL > inR) return null;
        int rootVal = pre[p++];
        TreeNode root = new TreeNode(rootVal);
        int mid = idx.get(rootVal);
        root.left  = build(inL, mid - 1);
        root.right = build(mid + 1, inR);
        return root;
    }
}
```

```kotlin
class Solution {
    private lateinit var idx: Map<Int, Int>
    private lateinit var pre: IntArray
    private var p = 0
    fun buildTree(preorder: IntArray, inorder: IntArray): TreeNode? {
        pre = preorder
        idx = inorder.withIndex().associate { (i, v) -> v to i }
        return build(0, inorder.lastIndex)
    }
    private fun build(inL: Int, inR: Int): TreeNode? {
        if (inL > inR) return null
        val v = pre[p++]
        val mid = idx[v]!!
        return TreeNode(v).apply {
            left  = build(inL, mid - 1)
            right = build(mid + 1, inR)
        }
    }
}
```

**복잡도** — O(n) / O(n) (map + 재귀 스택).

**함정**:
- preorder 인덱스 `p`는 **전역 또는 가변 참조** — 좌서브트리 다 만든 뒤 정확히 거기서 이어 우서브트리 root를 가져와야 함.
- HashMap 없이 inorder에서 매번 선형 탐색하면 O(n²) — skew 트리에서 TLE.
- 좌·우 분할은 inorder의 mid 기준, preorder는 순서대로 소비.

---

### 6.9 LeetCode 297 — Serialize and Deserialize Binary Tree

**요약** — 트리를 문자열로 인코딩하고 다시 복원.

**접근** — preorder + null marker(`#`). queue로 deserialize.

(코드는 §3.5와 동일.)

```java
public class Codec {
    public String serialize(TreeNode root) {
        StringBuilder sb = new StringBuilder();
        ser(root, sb);
        return sb.toString();
    }
    void ser(TreeNode n, StringBuilder sb) {
        if (n == null) { sb.append("#,"); return; }
        sb.append(n.val).append(',');
        ser(n.left,  sb);
        ser(n.right, sb);
    }
    public TreeNode deserialize(String data) {
        Deque<String> q = new ArrayDeque<>(Arrays.asList(data.split(",")));
        return des(q);
    }
    TreeNode des(Deque<String> q) {
        String s = q.poll();
        if ("#".equals(s)) return null;
        TreeNode n = new TreeNode(Integer.parseInt(s));
        n.left  = des(q);
        n.right = des(q);
        return n;
    }
}
```

```kotlin
class Codec {
    fun serialize(root: TreeNode?): String = buildString {
        fun go(n: TreeNode?) {
            if (n == null) { append("#,"); return }
            append(n.`val`).append(',')
            go(n.left); go(n.right)
        }
        go(root)
    }
    fun deserialize(data: String): TreeNode? {
        val q: ArrayDeque<String> = ArrayDeque(data.split(','))
        fun go(): TreeNode? {
            val s = q.removeFirst()
            if (s == "#") return null
            return TreeNode(s.toInt()).apply {
                left  = go(); right = go()
            }
        }
        return go()
    }
}
```

**복잡도** — O(n) / O(n).

**함정**:
- null marker가 없으면 같은 inorder/preorder를 가진 두 트리 구분 불가.
- 구분자(`,`)가 값에 포함되면 안 됨 — 음수 처리 OK, 콤마 포함 문자열이면 변경.
- BFS 기반 직렬화(level-order + null)도 가능 — LeetCode 입력 표기와 같은 형식.

**Production 연결**:
- React Server Components는 컴포넌트 트리를 직렬화해 wire로 보냄.
- JVM의 `Serializable` (이제는 안티패턴이지만), Protobuf의 nested message가 사실상 트리 직렬화.

---

### 6.10 LeetCode 230 — Kth Smallest Element in a BST

**요약** — BST에서 k번째 작은 값.

**접근** — inorder가 정렬이라는 성질 활용. iterative inorder를 돌며 카운터 감소, 0 되면 반환.

```java
public int kthSmallest(TreeNode root, int k) {
    Deque<TreeNode> stack = new ArrayDeque<>();
    TreeNode cur = root;
    while (cur != null || !stack.isEmpty()) {
        while (cur != null) {
            stack.push(cur);
            cur = cur.left;
        }
        cur = stack.pop();
        if (--k == 0) return cur.val;
        cur = cur.right;
    }
    return -1; // unreachable
}
```

```kotlin
fun kthSmallest(root: TreeNode?, k: Int): Int {
    var remain = k
    val stack = ArrayDeque<TreeNode>()
    var cur = root
    while (cur != null || stack.isNotEmpty()) {
        while (cur != null) { stack.addLast(cur); cur = cur.left }
        cur = stack.removeLast()
        if (--remain == 0) return cur.`val`
        cur = cur.right
    }
    return -1
}
```

**복잡도** — O(h + k) / O(h). 재귀 inorder는 O(n) 전부 돌지만, iterative + early return은 k 도달 즉시 종료.

**꼬리질문 (LC 230 follow-up)** — "트리가 자주 수정되고 kth가 자주 호출된다면?" → 각 노드에 **subtree 크기**를 저장. `leftSize + 1 == k`면 root, `k ≤ leftSize`면 좌, 아니면 우로 가며 `k -= leftSize + 1`. O(h)로 단축. (Order Statistics Tree)

---

## 7. 함정·엣지케이스

### 7.1 모든 트리 코드의 첫 줄은 null 체크

```java
if (root == null) return ...;   // base case — 빼먹으면 NPE
```

LC 모든 트리 문제의 입력이 null일 수 있다는 가정으로 짜라. 재귀 함수 첫 줄에 무조건 null guard.

### 7.2 BST validate에서 범위 전파를 안 하면 미세하게 틀린다

```
       5
      / \
     1   4        ← 4 < 5 (좌 자식) OK
        / \
       3   6      ← 6 > 5 인데 5의 좌서브트리 안 — BST 아님
```

부모만 비교하면 `4 < 5` OK, `3 < 4` OK, `6 > 4` OK로 통과시켜버린다. **반드시 범위(low, high) 전파**.

### 7.3 직렬화 구분자 / null marker

```
"1,2,#,#,3,#,#"
```

- 구분자가 값에 포함되면 안 됨.
- null marker 없으면 같은 시퀀스를 다르게 해석.
- 음수 값: `"-5,..."` — split('-')은 안 됨, split(',') 사용.
- 빈 트리: `"#,"` — deserialize에서 즉시 null 반환.

### 7.4 좌·우 자식 swap 실수 (LC 226)

```java
// 틀린 코드 — 두 번째 줄에서 root.left는 이미 덮인 상태
root.left  = invertTree(root.right);
root.right = invertTree(root.left);   // ← 의도와 다른 subtree

// 올바른 코드
TreeNode l = invertTree(root.left);
TreeNode r = invertTree(root.right);
root.left  = r;
root.right = l;
```

### 7.5 LCA에서 자기가 자기의 조상

LC 235/236 정의: "노드는 자신의 ancestor가 될 수 있다." `if (root == p || root == q) return root;` 라인을 빼먹으면 p가 q의 조상인 경우 q 쪽 subtree까지 내려가버려 잘못된 답.

### 7.6 inorder 재구성에서 인덱스 mid 찾기

inorder에서 root 위치를 매번 선형 탐색하면 skew 트리에서 O(n²). 반드시 **HashMap 전처리**(O(n) 공간, O(1) lookup).

### 7.7 큰 트리에서 재귀 스택 오버플로우

N=10⁵, skew tree(linked list 형태)면 재귀 깊이 10⁵ → JVM 기본 스택 부족. 대비:
- iterative + explicit stack 사용.
- 또는 `Thread`로 큰 스택을 가진 쓰레드에서 실행 (`new Thread(null, task, "name", 1<<26).start()`).
- 또는 JVM 옵션 `-Xss8m` (코딩 테스트에선 설정 불가, 면접 답변용).

### 7.8 BFS에서 queue size snapshot

```java
while (!q.isEmpty()) {
    int size = q.size();         // ← 반드시 snapshot
    for (int i = 0; i < size; i++) { ... }
}
```

snapshot 없이 `q.size()`를 루프 조건으로 쓰면 자식이 push되면서 한 반복 안에서 size가 커져 레벨 구분이 깨진다.

### 7.9 BST insert/delete의 균형 깨짐

naive BST는 sorted insert 시 skew → O(n). 면접에서 "production이라면 어떻게?" → `TreeMap` (RB Tree)을 쓰거나 직접 AVL/RB 구현. 코딩 테스트에선 보통 입력이 랜덤하다고 가정해도 OK, 단 worst case를 묻는 꼬리질문에 답변 준비.

### 7.10 leaf 정의 — "좌 == null AND 우 == null"

LC 111(min depth)에서 함정. "한쪽 자식만 있는 노드"는 leaf가 아니다. min depth 계산 시 leaf까지의 깊이 — `min(1+L, 1+R)`로 하면 한쪽이 0인 경우 0이 선택되어 틀린다. 한쪽이 null이면 그쪽은 leaf 후보가 아니므로 반대쪽만 본다.

---

## 8. 꼬리질문 트리

### 8.1 "Red-Black vs AVL 차이는?"

- AVL: 좌·우 높이 차 ≤ 1 — 더 엄격, 검색 약간 빠름, **write 시 회전 많음**.
- RB: 색 규칙(루트·leaf black, red 두 개 연속 금지, root→leaf black count 동일)으로 높이 ≤ 2 log(n+1) 보장 — 균형 느슨, **write 적은 회전**.
- Java `TreeMap`, Linux CFS, C++ `std::map`이 RB인 이유 — write/read 혼합 워크로드에서 안전.

### 8.2 "Trie 언제 쓰나?"

키가 **공통 prefix를 공유하는 문자열**일 때 — autocomplete, IP routing (longest prefix match), spell checker, T9 keypad. HashMap도 O(L)이지만 Trie는 prefix 쿼리(`startsWith`)가 자연스럽고 공간 공유 효과. LC 208(Implement Trie), 211, 212.

### 8.3 "Segment Tree는?"

배열의 **구간 집계(sum/min/max/gcd)와 단일/구간 update**가 둘 다 O(log n)으로 필요할 때. 시간복잡도 비교:

| 자료구조 | range query | point update | range update |
|---|---|---|---|
| naive 배열 | O(n) | O(1) | O(n) |
| prefix sum | O(1) | O(n) | O(n) |
| Segment Tree | O(log n) | O(log n) | O(log n) (lazy propagation) |
| Fenwick (BIT) | O(log n) | O(log n) | 어려움 |

### 8.4 "Fenwick(Binary Indexed Tree)은?"

prefix sum의 빠른 업데이트 버전. Segment Tree보다 코드 짧고 캐시 친화적. `i & -i` 트릭으로 lowbit 추출. 단점: range update + range query는 두 BIT 필요. competitive programming의 단골.

### 8.5 "DB B-Tree / B+Tree와 BST의 차이는?"

- BST/AVL/RB: 노드당 키 1개, 자식 2개 — **메모리 인덱스에 적합**.
- B-Tree: 노드당 키 다수(보통 수십~수백), 자식 다수 — **디스크 페이지 1개에 노드 1개**가 들어가 페이지 fetch당 분기 수 최대화 → tree 높이 낮춤.
- B+Tree: B-Tree + 데이터는 leaf에만, leaf끼리 linked list → **range scan O(k)**. Postgres, MySQL InnoDB 전부 B+Tree.
- 왜 안 깊은가 — 1억 row, fanout 1000이면 높이 약 3. 디스크 IO 3번에 점 lookup 끝.

### 8.6 "n-ary tree는?"

자식이 임의 개수. `List<TreeNode> children`. 트리 순회/높이/직렬화 본질은 같지만 좌·우 분기 없음. LC 429(level order n-ary), 589(preorder n-ary), 590(postorder n-ary).

### 8.7 "왜 BST가 아니라 hash table을 안 쓰나?"

- hash: 평균 O(1) get/put, **순서 없음**.
- BST: O(log n) get/put, **정렬·범위 쿼리·predecessor/successor·k-th** 가능.
- 순서 보존이 중요하면 BST(TreeMap), 단순 lookup이면 hash(HashMap). LRU 캐시는 hash + linked list, k 큰 정렬된 데이터는 BST.

### 8.8 "트리 직렬화는 preorder 외 방법은?"

- BFS(level-order) + null marker — LeetCode 입력 표기.
- postorder + 갯수 헤더.
- inorder 단독은 불가 (좌·우 경계 모호) — 반드시 다른 순회와 함께.
- nested 표현 `"1(2(4)(5))(3)"` — 일부 변형 문제에서 등장.

### 8.9 "Morris 순회의 idea와 단점?"

- idea: subtree의 rightmost predecessor의 right pointer를 자기 자신으로 thread해 부모로 돌아갈 길 확보.
- 장점: O(1) 추가 공간.
- 단점: 트리를 **일시적으로 수정** — 멀티스레드/읽기전용 트리에서 사용 불가, 복원 안 되면 트리 망가짐.

---

## 9. 다른 패턴과의 연결

### 9.1 DFS / BFS의 트리 특화

- DFS(챕터 08) = 트리 순회의 일반화. 트리는 사이클이 없어 `visited` 배열 없이 OK(부모만 빼면 됨).
- BFS(챕터 09) = level-order 순회의 일반화. 최단 거리·층별 합·트리 너비.

### 9.2 Heap = complete binary tree

Heap(챕터 05)은 **완전 이진 트리 + 부모 ≤ 자식(min) 또는 부모 ≥ 자식(max)**. 배열로 구현하지만 자료구조 본질은 트리. parent = `(i-1)/2`, left = `2i+1`, right = `2i+2`. priority queue, k-th 문제, 중앙값 스트림, Dijkstra.

### 9.3 Trie = 문자열 트리

각 노드가 한 문자, 자식이 알파벳 크기. prefix 공유로 공간 절약 + prefix 쿼리. LC 208, 211, 212. production: Redis의 `ZSET`은 skiplist이지만 prefix routing은 trie 기반.

### 9.4 Graph로의 확장 — 트리는 사이클 없는 그래프

트리 알고리즘이 그래프로 일반화될 때:
- DFS/BFS — `visited` 추가.
- LCA — 일반 DAG에서는 여러 LCA 가능(common ancestor가 여러 개).
- 트리 DP — 그래프 DP / SCC 후의 DAG DP.

### 9.5 DP(챕터 12) ↔ 트리 DP

DP의 본질 "작은 부분 문제로 큰 문제 해결"이 트리에서는 자식 → 부모로 자연스럽게 흐름. 1차원 DP가 배열 인덱스를 따라간다면, 트리 DP는 post-order로 흐른다.

### 9.6 Segment Tree / Fenwick — 트리로 보는 배열

배열 위에 트리를 얹어 구간 쿼리를 가속. 트리 본질(parent ↔ children 관계)이 배열 처럼 보이는 자료구조의 뒤에 숨어있다.

### 9.7 Production 시스템에서의 트리 — 종합

| 영역 | 자료구조 | 챕터 14에서 본 어느 패턴과 |
|---|---|---|
| 파일시스템 inode | n-ary tree | DFS, post-order(`du`) |
| DOM | n-ary tree | pre-order(rendering), event bubbling(post-order) |
| Spring `ApplicationContext` | parent ↔ child BeanFactory | LCA 비슷한 lookup delegation |
| DB B+Tree | 다차 균형 트리 | BST의 디스크 확장 |
| Git commit graph | DAG | LCA = merge-base |
| React Fiber | linked tree | pre-order render, post-order commit |
| JVM PSYoungGen | (Eden + Survivor) — 트리는 아니지만 reachability는 DFS | DFS |
| Trie in IP router | trie | prefix 트리 |
| Kafka rebalance | controller tree | post-order propagation |
| Kubernetes ownerReferences | DAG | cascading delete = post-order |
| AST in compiler | n-ary tree | pre-order(symbol resolution), post-order(code gen) |

→ 트리 알고리즘 = **production system의 보편 어휘**. 면접에서 "트리 패턴은 어디 쓰는가" 물으면 위 표 중 2-3개를 자연스럽게 끌어와 답할 수 있어야 마스터 신호.

---

## 10. 백지 마스터 체크리스트

이 챕터를 백지에서 줄줄 풀어낼 수 있다면 마스터.

- [ ] TreeNode 정의를 LeetCode 시그니처로 외워서 쓴다.
- [ ] pre/in/post/level 4순회를 재귀와 iterative 둘 다 30초 안에 작성한다.
- [ ] iterative inorder의 "좌로 끝까지 push → pop → 우" 로직을 그림으로 설명한다.
- [ ] BST validate에서 "부모 비교만으론 부족, 범위 전파 필요"한 반례를 그린다.
- [ ] LCA가 BST(O(h))와 일반 트리(O(n))에서 어떻게 다른지 즉답한다.
- [ ] 트리 DP 시그니처 — "위로 올릴 값과 여기서 갱신할 값 분리"를 LC 124/543/110에 적용한다.
- [ ] preorder + inorder로부터 트리 복원할 때 HashMap 전처리가 왜 필요한지 설명한다.
- [ ] 직렬화에 null marker가 왜 필수인지 반례를 든다.
- [ ] 재귀 스택 오버플로우가 트리 크기 어디서 터지는지, 어떻게 회피하는지 답한다.
- [ ] RB Tree와 AVL Tree의 trade-off를 답한다.
- [ ] DB의 B+Tree가 왜 BST가 아니라 다차 트리인지 설명한다.
- [ ] Spring `ApplicationContext` 트리 / Linux inode 트리 / Git commit DAG / Kubernetes ownerReferences를 트리 패턴으로 연결한다.

---

## 부록 A — 한눈에 보는 순회 4종 비교

```
       1
      / \
     2   3
    / \
   4   5

  pre  : 1 2 4 5 3        (자기 → 좌 → 우)
  in   : 4 2 5 1 3        (좌 → 자기 → 우)
  post : 4 5 2 3 1        (좌 → 우 → 자기)
  level: 1 2 3 4 5        (위에서 아래로, 좌에서 우로)

  - pre  → serialize, copy
  - in   → BST sorted, kth smallest
  - post → tree DP, deletion, evaluate expression
  - level→ shortest path, level grouping, right side view
```

## 부록 B — 트리 문제 30초 분류표

| 문제 키워드 | 패턴 | 대표 LC |
|---|---|---|
| "depth", "height" | post-order 재귀 | 104 |
| "balanced" | post-order + sentinel | 110 |
| "invert", "mirror" | post/pre swap | 226 |
| "same tree", "subtree" | 동시 재귀 | 100, 572 |
| "BST validate" | 범위 전파 또는 inorder | 98 |
| "BST search/insert" | O(h) 분기 | 700, 701 |
| "BST kth smallest" | inorder + counter | 230 |
| "BST range sum" | DFS + 가지치기 | 938 |
| "LCA in BST" | 값 비교 | 235 |
| "LCA in binary tree" | post-order combine | 236 |
| "level order", "level avg" | BFS + size snapshot | 102, 199, 637 |
| "diameter", "longest path" | post-order + 전역 갱신 | 543, 124 |
| "construct from preorder+inorder" | HashMap + 분할 | 105, 106 |
| "serialize/deserialize" | preorder + null marker | 297 |
| "path sum" | DFS + running sum | 112, 113, 437 |
| "house robber on tree" | 트리 DP (취/안취 2상태) | 337 |
| "max path sum" | post-order, 음수 절단 | 124 |
| "right side view" | BFS 마지막 또는 DFS 우선우 | 199 |
| "count complete tree" | log²n 트릭 | 222 |

이 표가 머리에 들어가면 실전에서 30초 분류가 자연스러워진다. 트리 패턴은 **재귀 정의를 보고 → 4가지 순회 중 어느 시점에 무엇을 record/return 하는가**만 결정하면 코드가 거의 자동으로 따라온다. 트리 마스터의 본질은 자료구조가 아니라 **재귀의 본질**을 본 것이다.
