# Algorithm Master — 라이브 코딩 테스트 합격 패턴 마스터

> "투포인터? 양쪽에서 좁혀오는 거" 라고 답하면 입문자.
> 마스터는 **문제를 30초 안에 패턴으로 분류**하고, Java/Kotlin 어느 쪽으로도 막힘없이 템플릿을 쓰며, 엣지 케이스(빈 배열, 단일 원소, 중복, 오버플로우)를 면접관이 묻기 전에 먼저 짚어낸다.
> 이 가이드는 hellointerview.com 순서를 기반으로, 대한민국 라이브 코딩 테스트(프로그래머스/LeetCode 스타일)를 통과하는 데 필요한 **16개 핵심 패턴**을 다룬다. 각 챕터는 개념·인지 신호·Java 템플릿·Kotlin 템플릿·대표 문제(프로그래머스 + LeetCode)·시간 복잡도·함정까지 포함한다.

---

## 📚 챕터 목록 (학습 순서 = hellointerview.com 순서)

| # | 패턴 | 파일 | 핵심 인지 신호 |
|---|---|---|---|
| 01 | **Two Pointers** | [01-two-pointers.md](./01-two-pointers.md) | "정렬된 배열에서 합·차·쌍 찾기", "in-place 변형", "양 끝에서 좁혀오기" |
| 02 | **Sliding Window** | [02-sliding-window.md](./02-sliding-window.md) | "연속된 부분 배열/문자열의 최대·최소·개수", "고정/가변 윈도우" |
| 03 | **Intervals** | [03-intervals.md](./03-intervals.md) | "구간 병합·삽입·겹침 판별", "정렬 후 sweep" |
| 04 | **Stack** | [04-stack.md](./04-stack.md) | "괄호 매칭", "monotonic stack", "next greater element" |
| 05 | **Heap (Priority Queue)** | [05-heap.md](./05-heap.md) | "top-K", "merge K sorted", "중앙값 스트림" |
| 06 | **Linked List** | [06-linked-list.md](./06-linked-list.md) | "Fast/slow pointer", "in-place reverse", "cycle 검출" |
| 07 | **Binary Search** | [07-binary-search.md](./07-binary-search.md) | "정렬된 배열 검색", "답을 이분 탐색 (parametric)", "lower/upper bound" |
| 08 | **DFS** | [08-dfs.md](./08-dfs.md) | "재귀로 깊이 우선", "트리/그래프 순회", "백트래킹 전 단계" |
| 09 | **BFS** | [09-bfs.md](./09-bfs.md) | "최단 거리 (가중치 없음)", "레벨별 순회", "큐 기반" |
| 10 | **Backtracking** | [10-backtracking.md](./10-backtracking.md) | "조합·순열·N-Queen", "선택 → 재귀 → 되돌리기" |
| 11 | **Graph** | [11-graph.md](./11-graph.md) | "Union-Find, Dijkstra, 위상정렬", "인접 리스트 vs 행렬" |
| 12 | **Dynamic Programming** | [12-dp.md](./12-dp.md) | "최적 부분 구조 + 중복 부분 문제", "메모이제이션 vs 타뷸레이션" |
| 13 | **Greedy** | [13-greedy.md](./13-greedy.md) | "지역 최적 = 전역 최적 증명 가능", "정렬 + 선택" |
| 14 | **Tree** | [14-tree.md](./14-tree.md) | "이진 트리 순회", "BST 성질", "LCA", "균형 트리" |
| 15 | **Prefix Sum** | [15-prefix-sum.md](./15-prefix-sum.md) | "구간 합 쿼리 O(1)", "차분 배열", "2D prefix sum" |
| 16 | **Matrix** | [16-matrix.md](./16-matrix.md) | "2D 그리드 순회", "회전/전치", "섬 개수 (DFS/BFS)" |

---

## 🎯 학습 목표

이 가이드를 마치면 다음이 가능해진다.

1. **문제 분류 30초** — 문제 설명만 읽고 어느 패턴에 속하는지 즉시 판단.
2. **Java/Kotlin 양손잡이** — 코딩 테스트 환경(프로그래머스 Java/Kotlin, LeetCode Java/Kotlin)에서 자유롭게 선택.
3. **템플릿 암기** — 16개 패턴 각각의 boilerplate를 백지에서 작성.
4. **엣지 케이스 자동 점검** — 빈 입력, 단일 원소, 중복, 오버플로우, 음수, off-by-one을 면접관이 묻기 전에 짚음.
5. **시간/공간 복잡도 즉답** — 코드를 쓰면서 동시에 복잡도를 말함.
6. **꼬리질문 방어** — "더 빠른 방법은?", "메모리를 줄이려면?", "스트리밍이라면?" 에 대비.

---

## 🧭 학습 철학 (flab-study AGENTS.md 5룰)

1. **개념 누락 금지** — 패턴의 본질·왜·연결까지
2. **시니어 운영 마스터 관점** — 라이브 코딩 + production 사고 패턴 모두 매핑
3. **표면 디테일 제외** — 옵션·문법 외우기보다 본질·왜·역사
4. **다이어그램 필수** — 모든 패턴을 ASCII로 시각화, 백지 그리기 가이드 포함
5. **백지 마스터 수준** — 30초에 패턴 분류, 5분에 정답 코드, 10분에 엣지 케이스까지

---

## 📐 각 챕터의 표준 구조

| 단계 | 내용 |
|---|---|
| 0. 인지 신호 | 문제에서 이 패턴을 감지하는 키워드·신호 |
| 1. 백지 그리기 | ASCII 다이어그램으로 패턴 시각화 |
| 2. 직관 | 한 줄 비유 + 정확한 정의 |
| 3. Java 템플릿 | boilerplate + 변형 (in-place, return index, return count …) |
| 4. Kotlin 템플릿 | 동일 패턴의 Kotlin 관용 표현 |
| 5. 시간/공간 복잡도 | 왜 그런지 근거까지 |
| 6. 대표 문제 (5~10개) | 프로그래머스 + LeetCode + 한국 코딩 테스트 빈출 |
| 7. 함정·엣지케이스 | off-by-one, 중복, 오버플로우, 빈 입력 |
| 8. 꼬리질문 | "더 빠르게?", "메모리 줄이려면?", "스트리밍?" |
| 9. 다른 패턴과의 연결 | 어떤 패턴으로 확장되는가 |

---

## 🔗 문제 출처

- **프로그래머스** (programmers.co.kr) — 한국 코딩 테스트 표준
- **LeetCode** (leetcode.com) — 글로벌 표준, 패턴별 최고 학습 자료
- **백준** (acmicpc.net) — 알고리즘 분류별 다양한 난이도
- **hellointerview.com/learn/code** — 패턴 분류 기준
