# flab — Deep Study Repository

**"백지에서 창시자·마스터 수준까지"** 깊이 학습하기 위한 자료 저장소.
JVM에서 시작해 객체지향·네트워크·Java 내부·알고리즘·실전 아키텍처 마이그레이션까지 확장된다.

각 토픽의 목표는 하나다 — **백지에서 그 주제를 줄줄 풀어 설명하고, production에서 어떤 장애로 드러나는지 진단·해결할 수 있는 마스터 수준.**

---

## 📚 챕터 (디렉토리)

| 디렉토리 | 한 줄 정의 | 핵심 내용 |
|---|---|---|
| **[jvm/](./jvm/)** | JVM을 창시자 수준까지 | Verifier·ClassLoader·Linking → Runtime Data Areas(Heap/TLAB) → Execution Engine(인터프리터·JIT C1/C2) → GC(G1·Mixed) → Threading·Safepoint → HotSpot 내부·GraalVM. 운영 시나리오·실습 워크북·트레이드오프 표·모의면접 포함 |
| **[oop/](./oop/)** | 객체지향을 설계 권위자 수준까지 | 객체·협력 → 추상화·캡슐화 → 책임 할당 → 메시지·인터페이스 → 객체 분해 → 의존성 관리 → 유연한 설계 → 상속 vs 합성 → 함수형 패러다임 → Java 진화·Kotlin 패러다임·Spring. 운영·워크북·트레이드오프·모의면접 포함 |
| **[network-request-lifecycle/](./network-request-lifecycle/)** | URL 한 줄 입력부터 DB 응답까지 한 줄기로 | URL 파싱·percent-encoding → DNS·라우팅 → OSI 7계층·TCP/TLS → 로드밸런서(L4/L7) → Nginx(epoll) → Tomcat(Acceptor·Poller·Executor) → 커넥션 풀(HikariCP) → JDBC wire protocol. `00-main-flow.md`가 면접용 마스터 한 줄기 |
| **[java-deep-dive/](./java-deep-dive/)** | Java 언어 기능의 내부 메커니즘 | 제네릭(type erasure·Signature·bridge method) · 리플렉션(MethodHandle·Dynamic Proxy) · 스레드(platform vs virtual·ThreadLocal·work-stealing) · 타임아웃(connection vs read의 OS 수준 차이) · 해싱과 해시 컬렉션 |
| **[algorithm-master/](./algorithm-master/)** | 라이브 코딩 테스트 합격 패턴 | 16개 핵심 패턴(투포인터·슬라이딩윈도우·구간·스택·힙·연결리스트·이분탐색·DFS·BFS·백트래킹·그래프·DP·그리디·트리·누적합·행렬). 패턴별 인지 신호 + Java/Kotlin 템플릿 + 대표 문제 + 함정 |
| **[cmong-architecture-migration/](./cmong-architecture-migration/)** | 실전 아키텍처 마이그레이션 케이스 | 외부 플랫폼 댓글 워크플로를 HTTP 동기 → RabbitMQ 비동기로 전환 · 메시지 큐 도입 후 Consumer 단건 UPDATE 폭주를 푸는 micro-batching 패턴 · as-is/to-be 아키텍처 다이어그램(Excalidraw) |

---

## 🎯 공통 학습 철학

모든 토픽이 같은 룰(see [AGENTS.md](./AGENTS.md))을 따른다:

1. **개념 누락 금지** — 핵심 개념은 본질·왜·역사·연결까지 빠짐없이
2. **시니어 운영 마스터 관점** — 이 지식으로 production에서 어떤 문제를 어떻게 진단·해결하는지 항상 매핑
3. **표면 디테일 제외** — hex 값·비트 자릿수·옵션값 외우기 같은 표면 정보는 빼고 본질·왜·역사·연결만
4. **시각화 필수** — 핵심 개념을 그림(Excalidraw / ASCII / Mermaid)으로, 백지에서 그리며 학습 가능하게
5. **마스터 수준 목표** — 주제를 백지에서 줄줄 풀어 설명할 수 있게

각 챕터는 입문자의 답과 마스터의 답을 대조하며 시작하고(README 상단), **꼬리질문 트리**(3단 이상 깊이)로 면접을 시뮬레이션한다. 어려운 토픽은 `📌 ... — 클릭해서 펼치기` 토글로 용어·약자를 그 자리에서 풀어준다.

---

## 🛠 사용법

각 챕터의 README가 그 챕터의 학습 흐름을 안내한다. SVG 다이어그램은 md 파일에 인라인 임베드되며, 편집은 `.excalidraw` 파일을 [excalidraw.com](https://excalidraw.com/)에서 열어 가능하다.

```bash
# Excalidraw 다이어그램 재생성 (jvm / oop 등 _tools 보유 챕터)
cd jvm        # 또는 oop
python3 _tools/gen_excalidraw.py
```
