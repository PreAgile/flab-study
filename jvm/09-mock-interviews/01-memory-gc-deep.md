# 09-01. Memory + GC — 시니어 깊이 답변 8문항

> 이 문서는 자바 시니어 면접에서 "메모리 구조와 GC"를 줄줄 답하기 위한 **답안 모음집**이다.
> 각 답안은 **한 줄 정의 → 본질·왜·연결 → 코드/ASCII 도식 → 운영 진단(jcmd/JFR/NMT) → 한 줄 정리** 구조.
> 표면 디테일(hex, 비트 자릿수)은 뺐다. 본질·역사·왜·연결만 남겼다.
> 시니어 마스터 목표 — 백지에서 8문항을 다 풀어낼 수 있을 것.

---

## 목차

1. JVM의 메모리 구조 (Heap/Stack/Method Area/PC/Native) 와 GC가 작동하는 영역
2. Young/Old Generation 차이와 동작 (Eden/Survivor/Promotion/Card Table)
3. G1/CMS/ZGC 내부 (RSet/SATB/Colored Pointer/Read Barrier)
4. JVM 튜닝 — 메모리 영역별 파라미터의 의미와 영향
5. 메모리 릭 시나리오 (ThreadLocal/static/ClassLoader/Listener) 와 진단
6. Native Memory Tracking (NMT) 실전
7. GC Pause Time 줄이기 — 실무 전략
8. 컨테이너 환경에서 달라지는 JVM 메모리 (cgroup awareness)

---

# 1. JVM 메모리 구조와 GC의 작동 범위

> **한 줄 정의**: JVM 메모리는 "**스레드별 영역(Stack, PC, Native Stack)**" + "**전체 공유 영역(Heap, Method Area)**"의 두 축으로 나뉘고, **GC는 Heap과 Method Area(Metaspace)에만 작동**하며 나머지는 스레드 생명주기에 의해 자동 해제된다.

## 1.1 본질 — 왜 5개 영역인가

JVM Spec이 5개 영역을 정의한 이유는 단순한 분류가 아니라, **각 영역이 다른 lifetime과 다른 소유자**를 갖기 때문이다.

```
                       [JVM Process Memory]
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
   [공유 영역]               [스레드별 영역]          [JVM 자체]
   (GC 대상)                 (GC 대상 아님)         (C++ heap)
        │                       │                       │
   ┌────┴────┐         ┌────────┼────────┐         ┌────┴────┐
   │         │         │        │        │         │         │
 Heap   Method Area  JVM      PC      Native    Code      C-Heap
        (Metaspace) Stack    Reg     Stack     Cache     (JNI/buffer)
```

- **Heap** — `new`로 생성되는 모든 객체. 모든 스레드 공유. **GC의 주 무대**.
- **Method Area / Metaspace (Java 8+)** — 클래스 메타데이터, 메서드 코드 정보, 상수 풀, static 변수. **공유 + GC 대상이지만 별도 ClassLoader 단위로 해제**.
- **JVM Stack** — 스레드마다 1개. 메서드 호출 시 Stack Frame이 push, return 시 pop. Local variable, operand stack, return address. **메서드가 끝나면 사라지므로 GC 불필요**.
- **PC Register** — 스레드마다 1개. 현재 실행 중인 bytecode 주소. native 메서드일 때는 undefined.
- **Native Method Stack** — JNI 호출 시 native 함수의 스택. C/C++ 코드용. JVM 외부 메모리.

## 1.2 왜 GC는 Heap과 Metaspace에만 작동하는가

Stack/PC는 **frame이 push/pop**되며 자동 정리되므로 별도 회수 필요 없음. Native Stack은 OS 영역이라 JVM이 관리 안 함. **불확정한 lifetime을 가진 영역**만 GC가 필요한데, 그게 정확히 Heap (객체)과 Metaspace (클래스)다.

```
Stack:   메서드 진입 → frame push → 메서드 종료 → frame pop  (확정적)
Heap:    new 시점 → ??? → 더 이상 참조 없을 때                 (불확정 → GC 필요)
Metaspace: ClassLoader.defineClass → ??? → ClassLoader unreachable (불확정 → GC 필요)
```

## 1.3 Heap 내부 — Generational 가설

Heap은 평탄한 영역이 아니라 **Young (Eden + S0 + S1) + Old**로 세대 분리. 근거는 **"대부분의 객체는 일찍 죽는다"는 weak generational hypothesis**. → Young을 자주, Old를 가끔 청소하면 효율적.

```
[Heap]
┌─────────────────────────────────────────────────────────┐
│  Young Generation                  │   Old Generation   │
│  ┌──────────┬───────┬───────┐      │                    │
│  │  Eden    │ S0    │ S1    │      │   Tenured space    │
│  └──────────┴───────┴───────┘      │                    │
└─────────────────────────────────────────────────────────┘
   ↑                                    ↑
   Minor GC (잦음, 빠름)                Major/Full GC (드뭄, 길다)
```

## 1.4 Metaspace의 역사 — 왜 PermGen이 사라졌는가

Java 7까지는 Method Area를 PermGen (Permanent Generation) 으로 Heap 내부에 두었음. 문제:

- PermGen은 **고정 크기 영역**. 동적 클래스 로딩(JSP, Groovy, dynamic proxy 많은 앱)에서 `OutOfMemoryError: PermGen space` 빈발.
- Heap의 일부라 GC 압박을 같이 받음.

Java 8에서 **Metaspace로 이전**. 특징:

- **Native memory (C-heap) 사용** → OS 한계까지 동적 확장.
- `-XX:MaxMetaspaceSize` 미설정 시 무한 증가 → 새로운 메모리 릭 패턴 등장.
- GC는 ClassLoader 단위로 발생 — ClassLoader가 unreachable해야 그 안의 클래스 전체가 회수됨.

## 1.5 운영 진단 — 영역별 도구 매핑

| 영역 | 진단 도구 | 무엇을 보는가 |
|---|---|---|
| Heap | `jcmd <pid> GC.heap_info`, `jmap -histo`, JFR (`-XX:StartFlightRecording`) | live set, allocation rate, retained size |
| Metaspace | `jcmd <pid> VM.metaspace`, `jstat -gc` (MC/MU) | class count, loader 누수 |
| Code Cache | `jcmd <pid> Compiler.codecache`, `-XX:+PrintCodeCache` | nmethod size, sweeper 활동 |
| Native | `jcmd <pid> VM.native_memory summary` (NMT) | thread/class/internal/symbol |
| Stack | `jstack <pid>`, async-profiler | 깊이, 무한 재귀, deadlock |

## 1.6 시니어 한 줄

> "**Heap과 Metaspace만 GC 대상**이고, 나머지 영역(Stack/PC/Native)은 **스레드 lifecycle에 묶여 자동 정리**된다. 그래서 production에서 OOM을 만나면 첫 질문은 '**어느 영역의 OOM인가**' — Java heap OOM은 jmap, Metaspace OOM은 ClassLoader leak, Native OOM은 NMT로 진단 경로가 완전히 다르다."

---

# 2. Young / Old Generation 과 GC 알고리즘 동작

> **한 줄 정의**: Young Generation은 **Copy 알고리즘 + Eden/Survivor 구조**로 짧게 사는 객체를 빠르게 회수하고, Old Generation은 **Mark-Sweep-Compact 또는 Region 기반**으로 오래 사는 객체를 가끔 길게 회수한다. 둘을 잇는 다리가 **Promotion**과 **Card Table**.

## 2.1 본질 — 왜 두 세대로 나누는가

**Weak Generational Hypothesis** — 객체의 사망률은 나이에 반비례. 대부분 객체는 짧게 살고, 살아남은 일부는 오래 산다.

```
객체 생존 곡선:
사망률
  │
 100%│██
     │██▓▓
     │██▓▓▒▒
     │██▓▓▒▒░░░░░___________________
     └─────────────────────────────► 객체 나이
     0   1   2   3   ...   많음

→ 어차피 대부분 죽을 거면 작은 영역에 모아두고 자주 청소
   살아남은 소수만 Old로 보내서 가끔 청소하면 효율적
```

## 2.2 Young Generation 동작 — Copy 알고리즘

```
[초기 상태]
Eden:    [A][B][C][D][E][F][G][H]   ← 새 객체는 모두 여기 할당
S0:      [   비어있음   ]
S1:      [   비어있음   ]

[Minor GC: A,C,F만 살아있음 — S0로 copy + age=1]
Eden:    [          비움          ]
S0:      [A:1][C:1][F:1]
S1:      [   비어있음   ]

[다음 Minor GC: C,F만 살아있음 — S1로 copy + age=2]
Eden:    [          비움          ]
S0:      [   비움   ]
S1:      [C:2][F:2]

[age >= MaxTenuringThreshold → Old로 Promotion]
Old:     [...기존...][F]
```

**왜 Copy인가** — Mark-Sweep은 fragmentation 발생, Mark-Compact는 compaction 비용. **Copy는 살아있는 객체만 복사**하므로 객체 대부분이 죽는 Young에서는 가장 효율적. **단점: 메모리의 절반(S0 or S1)은 항상 비워둠**. 그래도 Young은 작아서 OK.

## 2.3 Promotion — Young → Old

```
승격 조건 (둘 중 하나):
1) age >= MaxTenuringThreshold (기본 15, GC ergonomics로 동적 조정)
2) Survivor 공간 부족 → 즉시 Old로 (Premature Promotion)
```

**Premature Promotion이 문제** — 본래 짧게 살 객체가 Survivor가 작아서 Old로 넘어가면, Old에 쓸데없는 쓰레기가 쌓이고 Major GC를 유발. **Survivor 크기 부족 = 운영 시 가장 흔한 튜닝 포인트**.

## 2.4 Card Table — Young 단독 GC의 정확성을 보장하는 트릭

**문제 상황**:
```
Old gen:   [Object X] ──참조──> Young gen: [Object Y]
                                                │
                                                ↓
                            Y는 Old의 X에서 참조되니까 살아있어야 함
                            그런데 Minor GC는 Young만 봄
                            → Old 전체를 스캔해야 정확? → 너무 비쌈
```

**해법: Card Table** — Old gen을 카드 단위(보통 512B 카드)로 나누고, **Old → Young 참조가 생길 때마다 해당 카드를 "dirty"로 마킹**. Minor GC 시 dirty 카드만 스캔하면 됨.

```
Old gen을 카드 단위로 쪼갬:
┌──────┬──────┬──────┬──────┬──────┬──────┐
│ card0│ card1│ card2│ card3│ card4│ card5│
└──────┴──────┴──────┴──────┴──────┴──────┘
                │
   bytecode `putfield` 시 → write barrier:
   "이 필드의 카드 번호를 dirty로 마킹"

Card Table (1 byte per card):
[0][1][0][1][0][0]  ← 1 = dirty

Minor GC: dirty 카드 안의 객체만 root로 포함 → 정확하면서 빠름
```

**Write Barrier의 비용** — 모든 reference write에 카드 마킹 코드 삽입. 보통 2~3 instruction. **JIT가 inline**하므로 부담 적음. G1, ZGC는 더 정교한 RSet/SATB로 발전.

## 2.5 Old Generation 동작

| 알고리즘 | 특징 | 단점 |
|---|---|---|
| **Mark-Sweep** | live 객체 mark → dead 영역 free list로 회수 | fragmentation → allocation 느려짐 |
| **Mark-Compact** | mark 후 살아있는 객체를 한쪽으로 압축 | compaction 비용 (객체 이동 + 참조 갱신) |
| **Region-based (G1)** | Old도 region으로 쪼개 부분 compaction | 추가 metadata (RSet) |

Serial/Parallel GC는 Mark-Compact, CMS는 Mark-Sweep (마지막에 가끔 Full GC로 Compact), G1은 Region 기반.

## 2.6 운영 시나리오

```bash
# Eden 할당률 / Survivor 사용량 / Promotion율 보기
jcmd <pid> GC.heap_info
jstat -gcutil <pid> 1s

# GC 로그로 흐름 추적 (Java 11+)
-Xlog:gc*:file=gc.log:time,uptime,level,tags

# JFR로 allocation site 추적
jcmd <pid> JFR.start duration=60s filename=alloc.jfr settings=profile
```

**증상별 진단**:

| 증상 | 원인 후보 | 조치 |
|---|---|---|
| Minor GC 너무 잦음 | Eden 부족 / allocation rate 폭증 | -Xmn 증가, allocation site 찾기 |
| Survivor overflow → Premature Promotion | Survivor 부족 | SurvivorRatio 조정, 또는 단명 객체 줄이기 |
| Old gen 빠르게 참 | promotion rate 높음 / 진짜로 long-lived 객체 많음 | heap dump로 retained size 확인 |
| Full GC 잦음 | Old fragmentation (CMS) / 단순 부족 | G1/ZGC 전환, Xmx 증가 |

## 2.7 시니어 한 줄

> "Young은 **Copy로 빠르게**, Old는 **Mark-Compact로 가끔 길게**. 둘을 잇는 다리가 **Promotion과 Card Table**. 운영에서 80%의 GC 이슈는 '**Premature Promotion**' — Survivor가 너무 작아서 단명 객체가 Old로 넘어가는 패턴이다."

---

# 3. G1, CMS, ZGC — 최신 GC의 내부 동작

> **한 줄 정의**: CMS는 **concurrent mark-sweep**으로 pause를 줄였지만 fragmentation으로 망했고, G1은 **region 분할 + RSet + SATB**로 예측 가능한 pause를, ZGC는 **colored pointer + load barrier**로 sub-millisecond pause를 달성했다. 셋의 핵심은 "**concurrent 작업을 어떻게 정확히 하느냐**"의 진화사다.

## 3.1 진화의 큰 그림

```
[1세대: Stop-The-World 전체]
 Serial / Parallel GC
  - 모든 GC가 STW
  - 단순, 빠르지만 pause 길다
  - heap이 크면 수 초~수십 초 pause

[2세대: Concurrent Mark]
 CMS (Concurrent Mark Sweep, JDK 1.4~14에서 deprecate/제거)
  - mark는 concurrent, sweep도 concurrent
  - 단점: fragmentation → 결국 Full GC가 SerialGC로 fallback
  - "compaction이 없다"가 치명적

[3세대: Region 기반 + 예측 가능한 pause]
 G1 (Garbage First, JDK 7~, JDK 9 기본)
  - heap을 region(보통 1~32MB)으로 쪼갬
  - region별로 garbage 양 추적 → "garbage가 많은 region부터" 회수
  - MaxGCPauseMillis 목표로 region 개수 동적 선택
  - RSet, SATB로 concurrent 정확성 확보

[4세대: Sub-millisecond pause]
 ZGC (JDK 11~ experimental, JDK 15 production)
  - colored pointer (pointer의 상위 비트를 GC metadata로 사용)
  - load barrier (참조 읽을 때 pointer 검사 + 필요시 수정)
  - relocation도 concurrent
  - heap 16TB까지 sub-ms pause

 Shenandoah (RedHat, ZGC와 유사 철학)
  - Brooks pointer (각 객체에 forwarding pointer)
  - 32bit/64bit 모두 지원
```

## 3.2 G1 — RSet (Remembered Set)

**문제 상황**: Region을 단독으로 회수하려면 "이 region 밖에서 region 안 객체를 가리키는 참조"를 알아야 함. Card Table만으로는 부족 (Card Table은 Old→Young만).

**해결**: 각 region마다 **RSet 자료구조** — "**나(이 region)를 가리키는 다른 region의 location들**" 을 저장.

```
Region A          Region B          Region C
[obj1] ───┐       [obj3]            [obj5]
[obj2]    └────►  [obj4] ◄───────── [obj6]

Region B의 RSet = {Region A의 obj1 위치, Region C의 obj6 위치}

→ Region B를 단독으로 회수할 때
   RSet에서 root를 가져와 obj3,obj4의 reachability 판단
```

**RSet의 비용** — 모든 cross-region write에 RSet 업데이트 필요. **write barrier가 CMS보다 무거움**. Throughput은 Parallel GC보다 낮음. 대신 pause 예측 가능.

## 3.3 G1 — SATB (Snapshot-At-The-Beginning)

**문제 상황**: concurrent marking 중에 mutator가 reference를 바꾸면, 살아있는 객체를 dead로 잘못 판단할 수 있음.

**Tri-color marking**:
- White: 아직 안 본 객체
- Gray: 봤지만 자식 미탐색
- Black: 자식까지 다 탐색 완료

**위험 시나리오**:
```
1) Gray A → White B 참조
2) GC가 A 탐색 전, mutator가 A→B 참조 끊고 B를 Black C에 추가
3) GC가 A 탐색 시 B 안 보임 → B를 White로 판단
4) C는 Black이라 재탐색 안 함 → B는 살아있는데 dead로 판단됨!
```

**SATB의 해결책** — concurrent marking이 시작될 때의 스냅샷을 기준으로, 그 시점에 reachable했던 객체는 모두 살았다고 간주. **참조가 끊어지기 전의 값을 SATB queue에 저장 (pre-write barrier)**.

```
SATB write barrier:
  oldValue = obj.field  // 현재 값 (끊어지기 전)
  satb_queue.push(oldValue)  // 저장
  obj.field = newValue       // 새 값 쓰기
```

이렇게 하면 marking 시점에 살아있던 객체는 어떻게 참조가 바뀌어도 회수되지 않음. **단점: floating garbage** — 실제로는 죽은 객체도 이번 cycle에서는 살았다고 간주됨. 다음 cycle에 회수.

## 3.4 ZGC — Colored Pointer + Load Barrier

**핵심 아이디어** — 64bit 주소 공간은 어차피 다 안 쓰니까, **pointer 자체에 GC 상태 비트를 박자**.

```
[ZGC 64bit pointer 레이아웃 - 개념]
┌──────────────┬─────────────────────────────────────┐
│ color bits   │ actual address                      │
│ (M0,M1,Remap)│                                     │
└──────────────┴─────────────────────────────────────┘

color는 4가지 상태를 나타냄:
- Marked0 / Marked1 (현재 cycle / 다음 cycle)
- Remapped (relocation 끝났음)
- Finalizable
```

**Load Barrier** — 모든 reference load에 짧은 검사 코드 삽입.

```c
// 모든 obj.field 읽기 시:
ref = obj.field;
if (ref의 color가 현재 phase와 다르면) {
    ref = slow_path(ref);  // fixup: relocate / re-mark
    obj.field = ref;       // self-healing
}
return ref;
```

**Self-healing**의 의미 — 한 번 fixup된 pointer는 그 자리에 저장되므로, 두 번째 access는 fast path로 끝남. **점진적으로 모든 pointer가 정상화**.

**왜 read barrier로 충분한가** — G1은 reference write에 barrier (SATB). ZGC는 reference read에 barrier. 차이는:
- write barrier: 흔치 않은 작업 (write가 read보다 적음) → 그러나 정확성 보장 어려움 (SATB의 floating garbage)
- read barrier: 잦은 작업이지만 (read가 훨씬 많음), **relocation도 concurrent로 가능** → pause 극단적으로 짧음

**ZGC의 pause** — initial mark, remark 정도만 STW. 둘 다 root 스캔만이라 heap 크기와 무관 → **sub-ms pause**.

## 3.5 비교 표

| | CMS | G1 | ZGC | Shenandoah |
|---|---|---|---|---|
| Concurrent 단위 | mark, sweep | mark, partial copy | mark, copy 모두 | mark, copy 모두 |
| Compaction | 없음 (fallback Full GC) | region별 partial | full concurrent | full concurrent |
| Barrier | write (card) | write (RSet + SATB) | **load (read)** | **load + Brooks ptr** |
| Pause | 수십~수백 ms | 10~200 ms 목표 | <10 ms (보통 <1ms) | <10 ms |
| Heap 크기 한계 | 수십 GB까지 권장 | TB 가능 | 16 TB | TB |
| 단점 | fragmentation, 제거됨 | throughput↓ | CPU 사용량↑, throughput↓ | barrier 비용 |
| 운영 적합 | (deprecated) | 일반 서버 | 저지연 (실시간 API) | 저지연 (대안) |

## 3.6 운영 진단

```bash
# 어떤 GC가 돌고 있는지
jcmd <pid> VM.flags | grep -i gc

# GC 로그 (Java 11+)
-Xlog:gc*,gc+heap=debug,gc+ergo*=debug:file=gc.log:time,uptime,level

# G1 region 정보
jcmd <pid> GC.heap_info

# ZGC 통계
jcmd <pid> GC.stats   # ZGC는 자체 통계 제공
```

**증상별 매칭**:
- "p99 latency가 GC pause로 튄다" → G1 → ZGC 전환 검토
- "Full GC가 잦다" → CMS면 fragmentation, G1이면 humongous object 또는 mixed GC 실패
- "throughput이 떨어진다" → ZGC/Shenandoah의 barrier 비용 → Parallel GC 검토

## 3.7 시니어 한 줄

> "**CMS는 fragmentation으로 죽었고, G1은 region+RSet+SATB로 예측가능한 pause를, ZGC는 colored pointer+load barrier로 sub-ms pause를** 달성했다. 핵심은 'concurrent 작업 중 mutator가 끼어들 때 정확성을 어떻게 보장하느냐'의 진화 — write barrier (SATB)에서 read barrier (load)로 옮겨가며 pause를 줄였다."

---

# 4. JVM 튜닝 — 메모리 영역별 파라미터의 영향

> **한 줄 정의**: JVM 튜닝의 본질은 "**각 영역의 크기와 동적 확장 정책을 명시**해서 GC 빈도/길이/promotion 패턴을 예측 가능하게" 만드는 것이고, production에서는 거의 항상 **-Xms = -Xmx 고정 + MaxRAMPercentage + MaxMetaspaceSize 명시**로 시작한다.

## 4.1 영역별 파라미터 지도

```
[JVM 메모리 파라미터 큰 그림]
┌───────────────────────────────────────────────────────────┐
│ Heap                                                       │
│   -Xms <init>      -Xmx <max>      -XX:MaxRAMPercentage   │
│   ┌────────────────┬──────────────┐                       │
│   │ Young          │ Old          │                       │
│   │ -Xmn or        │ (Heap - Young)                       │
│   │ -XX:NewRatio   │                                       │
│   │   ┌──────┬──┬──┐                                      │
│   │   │ Eden │S0│S1│  -XX:SurvivorRatio                   │
│   │   └──────┴──┴──┘                                      │
│   └────────────────┴──────────────┘                       │
├───────────────────────────────────────────────────────────┤
│ Metaspace      -XX:MaxMetaspaceSize, MetaspaceSize        │
├───────────────────────────────────────────────────────────┤
│ Code Cache     -XX:ReservedCodeCacheSize                  │
├───────────────────────────────────────────────────────────┤
│ Thread Stack   -Xss                                       │
├───────────────────────────────────────────────────────────┤
│ Direct Buffer  -XX:MaxDirectMemorySize                    │
└───────────────────────────────────────────────────────────┘
```

## 4.2 -Xms / -Xmx — 가장 중요한 두 값

| 파라미터 | 의미 | 영향 |
|---|---|---|
| `-Xms` | 초기 heap | 작으면 시작 후 ergonomics가 점진 확장하며 GC 빈발 |
| `-Xmx` | 최대 heap | 너무 작으면 OOM, 너무 크면 GC pause↑ |

**실무 권장**: `-Xms = -Xmx`로 고정. 이유:
- 동적 확장 시 OS 메모리 페이지 할당으로 latency spike
- 컨테이너 환경에서 OOMKilled 위험 (확장 후 OS 한계 초과)
- ergonomics에 의한 GC 빈도 변화로 측정 어려움

## 4.3 -Xmn / NewRatio — Young 크기

```
-Xmn 직접 지정 (절대값)  vs  -XX:NewRatio=N (비율, Old:Young = N:1)
```

**언제 키워야 하나**:
- allocation rate가 매우 높음 → Eden 자주 참 → Minor GC 빈발 → Young을 키워야
- Survivor가 작아서 Premature Promotion 빈발 → Young을 키워야 (Survivor도 비례 확장)

**언제 줄여야 하나**:
- 객체 대부분이 진짜로 long-lived → Young을 작게 하고 Old를 크게 (예: cache 서버)

**G1에서는 -Xmn 대신** `G1NewSizePercent` / `G1MaxNewSizePercent` 사용. G1이 자동 조정하므로 명시는 보통 X.

## 4.4 SurvivorRatio — Premature Promotion의 주범

```
SurvivorRatio = Eden / Survivor
기본값 8 → Eden:S0:S1 = 8:1:1
```

Survivor가 너무 작으면 Minor GC 후 살아남은 객체가 Survivor에 안 들어가서 즉시 Old로 → Premature Promotion → Old gen 빠르게 참 → Major GC 잦음.

**진단**: `jstat -gcutil` 에서 S0/S1 사용률이 항상 ~100%면 부족.

## 4.5 MaxMetaspaceSize — Java 8 이후 새로 등장한 함정

**왜 위험한가** — 미설정 시 native memory를 무한히 사용. ClassLoader leak이 있어도 OOM 대신 OS swap → 노드 전체가 느려짐 → 진단 어려움.

**필수 설정**: `-XX:MaxMetaspaceSize=256m` (앱 규모에 따라). OOM이 빨리 나는 게 진단에 유리.

**진단 시점**:
- `OutOfMemoryError: Metaspace` → ClassLoader leak 의심 → heap dump에서 Loader 인스턴스 카운트
- Spring DevTools, Groovy/JRuby, dynamic proxy 다용도 앱은 특히 주의

## 4.6 ReservedCodeCacheSize — JIT가 쓰는 영역

Code Cache가 차면:
1. 새로운 메서드 컴파일 중단
2. 인터프리터로 회귀 (Tiered Compilation 후퇴)
3. 성능 급격히 떨어짐

기본은 240MB (JDK 11+). 마이크로서비스에서 큰 앱(Spring Boot, Kotlin coroutines, lambda 많은 코드)은 부족할 수 있음.

**진단**: `jcmd <pid> Compiler.codecache` → "CodeCache: size_max" 와 "used" 비교.

## 4.7 -Xss — 스레드 스택 크기

- 작게 (256K): 스레드를 많이 띄울 수 있음 (수천~수만)
- 크게 (1M~): 깊은 재귀 / 큰 local var 허용

**Stack 부족 증상**: `StackOverflowError` — Kotlin coroutines + JIT inlining + deep call chain 조합에서 종종.

**스레드 수 폭주 진단**: `jcmd <pid> VM.native_memory summary` → "Thread" 항목이 GB 단위면 스레드 풀 검토.

## 4.8 -XX:MaxDirectMemorySize — Direct ByteBuffer

NIO, Netty 등이 사용하는 native buffer. Java heap 외부. **기본값은 -Xmx와 동일**해서 컨테이너에서 의외로 큼.

릭 패턴: `ByteBuffer.allocateDirect()` 후 dereference만 하고 명시적 cleaner 호출 안 함. GC가 PhantomReference로 cleaner를 호출하지만 GC가 늦으면 native OOM.

## 4.9 운영 베이스라인 — production 시작 옵션 (예시)

```bash
# 8GB 컨테이너 기준
-XX:+UseG1GC                       # 또는 ZGC
-XX:MaxRAMPercentage=75.0          # heap = 컨테이너의 75%
-XX:InitialRAMPercentage=75.0      # heap 고정
-XX:MaxMetaspaceSize=256m          # 메타스페이스 상한
-XX:ReservedCodeCacheSize=512m     # Code Cache 여유
-XX:MaxDirectMemorySize=512m       # Direct buffer 상한
-XX:+HeapDumpOnOutOfMemoryError    # OOM 시 dump
-XX:HeapDumpPath=/var/log/app/
-Xlog:gc*:file=gc.log:time,uptime  # GC 로그
-XX:+ExitOnOutOfMemoryError        # OOM 시 즉시 종료 (K8s가 재시작)
```

## 4.10 시니어 한 줄

> "튜닝의 기본은 '**모든 메모리 영역의 상한을 명시**'다. -Xms=-Xmx 고정 + MaxMetaspaceSize + ReservedCodeCacheSize + MaxDirectMemorySize. 컨테이너에서는 RAMPercentage로 비율 지정. 그래야 OOM이 **빨리, 어느 영역인지 명확하게** 발생하고, 그 시점에 진단 도구를 붙일 수 있다."

---

# 5. 메모리 릭 시나리오와 진단

> **한 줄 정의**: Java의 메모리 릭은 **"의도와 다르게 GC root가 객체를 계속 참조하는 패턴"** 이고, 4대 패턴(**ThreadLocal, static collection, ClassLoader leak, Listener 미해제**) 이 production의 95%를 차지하며, 진단은 **heap dump → MAT의 Dominator Tree → retained size 큰 root 찾기** 의 정해진 흐름이다.

## 5.1 본질 — 왜 Java에서도 릭이 생기나

GC는 "도달할 수 없는 객체"를 회수한다. **도달 가능하면 GC는 손대지 않는다**. 따라서 의도와 무관하게 reference가 살아있으면 릭이다.

```
[릭의 정의]
[GC Root] ──► A ──► B ──► C ──► ...  계속 자라남
              ↑
       어딘가 의도하지 않은 long-lived reference

릭의 GC Root 후보:
1) 스레드 (active thread는 항상 root)
2) static field
3) JNI global reference
4) JVM 시스템 클래스의 reference
```

## 5.2 패턴 1: ThreadLocal Leak

```java
public class TenantContext {
    private static final ThreadLocal<Tenant> CURRENT = new ThreadLocal<>();
    public static void set(Tenant t) { CURRENT.set(t); }
    public static Tenant get() { return CURRENT.get(); }
    // remove() 안 부름!
}
```

**왜 릭인가**:
- 스레드 풀의 스레드는 **요청 처리 후 죽지 않고 재사용**
- ThreadLocalMap은 Thread 객체의 field → 스레드 살아있는 한 Map도 살아있음
- key는 weak reference (ThreadLocal 자체) 지만 **value는 strong reference**
- ThreadLocal 객체가 GC되어도 value는 남음 ("stale entry")
- 요청마다 Tenant 새로 set → ThreadLocalMap 에 누적

**해결**:
```java
try {
    TenantContext.set(tenant);
    process();
} finally {
    TenantContext.remove();   // 필수!
}
```

**진단**: heap dump → `Thread` 인스턴스의 `threadLocals.table[]` 들여다보기 (MAT의 "Path to GC Roots: ThreadLocal").

## 5.3 패턴 2: static Collection 무한 증가

```java
public class Cache {
    private static final Map<String, Object> CACHE = new HashMap<>();
    public static void put(String k, Object v) { CACHE.put(k, v); }
    // eviction 없음!
}
```

**왜 릭인가**: static field는 ClassLoader가 unload 안 되는 한 영원. 명시적 eviction 없으면 단조 증가.

**해결**: `Caffeine`, `Guava Cache` 등의 size-bounded / TTL cache 사용. 또는 `WeakHashMap` (key가 더 이상 참조되지 않으면 자동 제거).

**진단**: MAT의 Dominator Tree에서 **상위에 위치한 static Map** 찾기. retained size로 정렬.

## 5.4 패턴 3: ClassLoader Leak (Metaspace Leak)

가장 진단 어려운 패턴. 주로 **Tomcat redeployment, Spring DevTools, hot reload** 환경에서 발생.

```
[원인 시나리오]
1) App을 redeploy → 새 WebAppClassLoader 생성
2) 새 ClassLoader가 클래스 로드 + 객체 생성
3) 어딘가에서 "이전 ClassLoader가 로드한 객체"를 system static에 박음
   예: ThreadLocal이 옛 ClassLoader의 클래스 인스턴스 보유
       JDBC Driver registration (DriverManager)
       Logger 등록
4) 옛 ClassLoader가 unreachable이 안 됨 → unload 안 됨
5) Metaspace에 옛 클래스 메타데이터 남음
6) redeploy 반복 → Metaspace 단조 증가 → OOM Metaspace
```

**해결 코드 예** (web app shutdown hook):
```java
// JDBC Driver 명시적 deregister
DriverManager.deregisterDriver(driver);
// ThreadLocal 명시적 정리
context.remove();
// Logger 정리 (log4j2)
LogManager.shutdown();
```

**진단**: 
- `jcmd <pid> GC.class_stats` → 같은 클래스 이름이 여러 번 나오면 ClassLoader leak
- MAT의 "Duplicate Classes" 분석

## 5.5 패턴 4: Listener / Observer 미해제

```java
button.addListener(myListener);
// ... myListener은 큰 객체를 참조
// 버튼이 살아있는 한 myListener 살아있음
// removeListener 안 부름
```

**Spring Event, JMS Listener, JavaFX, Android lifecycle**에서 빈발.

**해결**: `WeakReference` 기반 listener, 또는 lifecycle 끝나면 명시적 remove.

## 5.6 진단 도구 체인

### Heap Dump 수집
```bash
# 정상 시점 baseline
jcmd <pid> GC.heap_dump /tmp/baseline.hprof

# 릭 의심 시점
jcmd <pid> GC.heap_dump /tmp/leak.hprof

# OOM 시 자동
-XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/var/log/
```

### Eclipse MAT (Memory Analyzer Tool)
1. **Histogram** — 클래스별 인스턴스 수와 retained size
2. **Dominator Tree** — "이걸 GC하면 얼마나 회수되나" 기준 정렬
3. **Path to GC Roots** — 의심 객체에서 root까지 경로 (왜 GC가 안 되는지)
4. **Leak Suspects Report** — 자동 분석 리포트 (보통 좋은 출발점)

### async-profiler — allocation 추적
```bash
# 어디서 객체가 많이 생성되는지 (allocation profiling)
./profiler.sh -d 60 -e alloc -f alloc.html <pid>
```

**언제 사용** — heap dump는 "쌓인 상태"를 보지만, async-profiler는 "**어디서 새로 생성되는지**" 를 본다. 둘을 조합.

### JFR (Java Flight Recorder)
```bash
jcmd <pid> JFR.start duration=300s filename=app.jfr settings=profile
# JDK Mission Control에서 분석
```

OLD object sample event로 long-lived 객체의 출처 추적.

## 5.7 진단 워크플로우 (실전)

```
1. 증상 확인: jstat -gc 1s → Old gen이 단조 증가?
2. 두 시점 heap dump 비교 (baseline vs leak time)
3. MAT Histogram → 비정상적으로 많은 클래스 식별
4. Dominator Tree → 그 클래스의 root 추적
5. Path to GC Roots → "왜 살아있나" 확인
6. 코드 fix → 검증 (다시 dump 비교)
```

## 5.8 시니어 한 줄

> "Java의 메모리 릭은 결국 '**의도하지 않은 strong reference가 어느 GC root에 연결되어 있다**' 한 줄로 요약된다. 4대 패턴(ThreadLocal, static Map, ClassLoader, Listener)을 외우고, 진단은 **heap dump 두 장 비교 → MAT Dominator Tree → Path to GC Roots** 가 정형화된 흐름이다. async-profiler로 allocation site까지 본다면 완벽하다."

---

# 6. Native Memory Tracking (NMT) 실전

> **한 줄 정의**: NMT는 JVM이 **자기 자신이 native memory(C-heap)를 어디에 얼마나 쓰는지 추적**해서 Heap 외부의 메모리 증가 원인 — Thread, Class, GC metadata, Code Cache, Direct Buffer, Symbol, JIT internal — 을 카테고리별로 보여주는 진단 도구이고, **컨테이너 OOMKilled의 95%는 NMT 없이는 진단 불가**다.

## 6.1 본질 — 왜 NMT가 필요한가

```
[Java 프로세스의 실제 메모리]
RSS (OS가 보는 메모리)
  =  Java Heap (-Xmx 안에)
  +  Metaspace (native)
  +  Code Cache (native)
  +  Thread stacks (native)
  +  GC structures (RSet, Mark bitmap, ...) (native)
  +  Direct ByteBuffer (native)
  +  JNI allocations (native)
  +  Symbol / String table (native)
  +  Compiler internal (native)
  +  JVM internal C++ heap
```

**OOMKilled 증상**: 컨테이너 memory limit = 4GB, -Xmx=3GB. 그런데 RSS가 4.2GB 까지 자라서 OS가 kill. **Heap dump는 깨끗** (3GB 안 채움). → 나머지 1.2GB가 어디서 왔는지?

→ **NMT가 답을 준다**.

## 6.2 NMT 활성화

```bash
# JVM 시작 시
-XX:NativeMemoryTracking=summary   # 또는 detail (오버헤드 ~5-10%)
```

**summary** vs **detail**:
- summary — 카테고리별 합계만
- detail — call site별 (어느 C++ 함수가 얼마나 alloc 했는지) — 디버깅 시

## 6.3 NMT 명령 — baseline / summary / detail / diff

### Baseline 저장
```bash
jcmd <pid> VM.native_memory baseline
```
이 시점의 상태를 "0점"으로 기억.

### Summary 보기
```bash
jcmd <pid> VM.native_memory summary
```

**출력 예 (실제 응답 예시)**:
```
Native Memory Tracking:

Total: reserved=5826MB, committed=4128MB

-                 Java Heap (reserved=3072MB, committed=3072MB)
-                     Class (reserved=1067MB, committed=80MB)
                            (classes #15234)
                            (instance classes #14000, array classes #1234)
-                    Thread (reserved=523MB, committed=523MB)
                            (thread #520)
                            (stack: reserved=519MB, committed=519MB)
-                      Code (reserved=251MB, committed=128MB)
-                        GC (reserved=180MB, committed=180MB)
-                  Compiler (reserved=18MB, committed=18MB)
-                  Internal (reserved=89MB, committed=89MB)
-                    Symbol (reserved=42MB, committed=42MB)
-     Native Memory Tracking (reserved=12MB, committed=12MB)
```

**해석 포인트**:
- **Thread: 523MB / 520개** → 스레드당 약 1MB. 스레드 수가 비정상.
- **Class: 80MB / 15234개** → ClassLoader leak 의심
- **GC: 180MB** → G1 RSet 또는 ZGC metadata. heap 큰 만큼 비례.
- **Code: 128MB** → JIT compiled code. ReservedCodeCacheSize 한도 내.

### Diff — 시간 경과 후 비교
```bash
# baseline 저장 → 시간 경과 → diff
jcmd <pid> VM.native_memory baseline
sleep 3600
jcmd <pid> VM.native_memory summary.diff
```

**diff 출력 핵심**:
```
-                    Thread (reserved=523MB +120MB, committed=523MB +120MB)
                            (thread #520 +100)
```
→ "1시간 동안 스레드가 100개, 120MB 증가" — 명확.

## 6.4 실전 시나리오

### Case 1: 컨테이너 OOMKilled, heap은 멀쩡

```
관찰:
- 컨테이너 limit 4GB
- -Xmx 3GB, heap 사용량 2.5GB
- RSS 4.1GB → OOMKilled

NMT 차이 (1주일 운영 후):
- Class: 80MB → 800MB (+720MB)
- thread #: 200 → 800 (+600)

→ 진단:
  1) Class 증가 → ClassLoader leak (Tomcat redeploy 패턴)
  2) Thread 증가 → ExecutorService 누수 (shutdown 안 부름)

→ 조치:
  1) MaxMetaspaceSize 명시
  2) ExecutorService.shutdown() in finally
  3) NMT diff 모니터링 자동화
```

### Case 2: Direct Buffer Leak (Netty)

NMT는 **JVM 자체의 native alloc**만 추적. Netty가 직접 호출하는 native alloc은 NMT에 안 잡힘. 하지만:

- NMT의 **Internal** 카테고리가 비정상 증가 → JNI 의심
- 또는 NMT는 정상인데 RSS만 증가 → JNI/native lib 의심
- 이 경우 **`pmap -x <pid>`** + **`jemalloc`의 heap profiling** 같은 OS 도구 필요

### Case 3: Code Cache Full

```
NMT:
- Code: reserved=240MB, committed=240MB (정확히 ReservedCodeCacheSize)
- 로그에 "CodeCache is full. Compiler has been disabled."

→ ReservedCodeCacheSize 512MB로 증가
```

## 6.5 NMT의 한계

- **JNI / 외부 native lib는 안 잡힘** — pmap, jemalloc 필요
- **Direct ByteBuffer는 일부만** — Java code의 allocateDirect는 잡힘, 그 안의 JNI/native는 별도
- **Heap 자체의 내부 구조는 안 보임** — 그건 heap dump 영역

## 6.6 운영 자동화 — NMT 모니터링 스크립트 예

```bash
#!/bin/bash
# nightly NMT diff for regression detection
PID=$(pgrep -f "myapp")
jcmd $PID VM.native_memory baseline
sleep 3600
jcmd $PID VM.native_memory summary.diff > /var/log/nmt_diff_$(date +%F).log
# 알람: Thread / Class / Internal 증가가 임계치 이상이면 Slack 알림
```

## 6.7 시니어 한 줄

> "**컨테이너 OOMKilled인데 heap dump가 깨끗하면, 답은 NMT에 있다**. baseline → summary → diff 흐름으로 Thread, Class, Code, GC, Internal 중 어느 카테고리가 자라는지 확인 → 패턴 매칭(스레드 누수, ClassLoader leak, JIT 폭증, GC metadata 비대). NMT가 부족하면 pmap + jemalloc 으로 한 단계 더 내려간다."

---

# 7. GC Pause Time 줄이기 — 실무 전략

> **한 줄 정의**: GC pause를 줄이는 본질은 "**STW 단계에서 하는 작업을 줄이거나(=root 스캔만 STW), concurrent로 옮기거나, region 크기를 작게 해서 단위 pause를 줄이는 것**" 이고, 실무 우선순위는 **① GC 알고리즘 선택(ZGC/Shenandoah로 전환) → ② Region/Young 크기 튜닝 → ③ Allocation 최적화(객체 할당 자체 줄이기)** 순이다.

## 7.1 본질 — Pause가 왜 생기나

```
[Generic GC cycle]
1. Initial Mark (STW)    ← root 스캔, 짧음
2. Concurrent Mark       ← mutator와 같이 돌음
3. Remark (STW)          ← mutator가 바꾼 거 정리, 보통 김
4. Concurrent Sweep      ← mutator와 같이 돌음
5. Compaction (STW)      ← G1: 일부, ZGC: 거의 없음

→ Pause = 1 + 3 + 5 합
→ ZGC: 3을 거의 없앰 (load barrier로 mutator 변경을 lazy 처리)
→ ZGC: 5도 concurrent (relocation도 mutator 진행 중)
```

## 7.2 전략 1: GC 알고리즘 전환

| | Parallel | G1 | ZGC | Shenandoah |
|---|---|---|---|---|
| 평균 pause | 100ms~수초 | 50~200ms | <10ms (보통 <1ms) | <10ms |
| 적합 | batch/throughput | 일반 서버 | latency 민감 | latency 민감 |
| JDK | 모두 | 9+ 기본 | 15+ production | 12+ (OpenJDK) |

**전환 결정**: 
- p99 latency가 GC pause 때문에 SLO 미달이면 → ZGC
- 단순 throughput만 중요 → Parallel
- 메모리 4GB 이하의 일반 서버 → G1로 충분

## 7.3 전략 2: G1 튜닝

### MaxGCPauseMillis
```bash
-XX:MaxGCPauseMillis=100   # 목표값. 강제는 아님
```

G1은 이 목표 달성을 위해 **매 GC마다 회수할 region 개수를 동적 결정**. 작게 하면 region 수가 줄어 pause는 짧지만 GC가 더 자주 발생 → throughput 손실.

### G1HeapRegionSize
```bash
-XX:G1HeapRegionSize=8m   # 1MB~32MB, heap 크기에 따라 자동 결정
```

작은 region → 더 정밀한 pause 제어. 큰 region → metadata 적음. **Humongous object(region 크기의 절반 이상)** 이 많으면 region 키워야.

### ParallelGCThreads / ConcGCThreads
```bash
-XX:ParallelGCThreads=N   # STW 단계의 병렬 스레드
-XX:ConcGCThreads=M       # concurrent 단계의 병렬 스레드
```

기본은 CPU 수에 비례. **컨테이너에서는 cgroup CPU limit 인식 못 하면 호스트 CPU 기준으로 설정** → JDK 10+ UseContainerSupport로 해결되지만 명시가 안전.

### 운영 노하우
- MaxGCPauseMillis는 **목표일 뿐**. 실제 pause가 더 길면 region 크기 / Young 크기 조정
- Young을 작게 하면 Minor GC가 짧아지지만 빈도 증가
- Young을 크게 하면 Minor GC pause↑이지만 promotion 감소

## 7.4 전략 3: ZGC 튜닝

ZGC는 자동 튜닝이 우수해서 만질 게 적음.

```bash
-XX:+UseZGC
-XX:ZCollectionInterval=120     # 최소 GC 간격 (초)
-XX:ZAllocationSpikeTolerance=2 # spike 허용도
-XX:+ZGenerational              # JDK 21+ Generational ZGC (성능 향상)
```

**Generational ZGC** (JDK 21+) — ZGC도 young/old 분리. 짧게 죽는 객체를 더 효율적으로 처리.

## 7.5 전략 4: Allocation 줄이기 (가장 효과적)

GC pause의 근본 원인은 **회수할 객체가 많다는 것**. 객체 생성 자체를 줄이면 pause는 자동으로 짧아진다.

**Allocation hot path 찾기**:
```bash
# async-profiler allocation mode
./profiler.sh -d 60 -e alloc -f alloc.html <pid>

# JFR allocation event
jcmd <pid> JFR.start duration=60s settings=profile
# Mission Control에서 "TLAB Allocation" 이벤트 분석
```

**전형적 줄이기 패턴**:
- String concat 루프 → StringBuilder
- Boxing 남발 (`Integer` 대신 `int`) → primitive 유지
- Stream에서 매번 `Optional.of` → null 직접 처리
- Logback `String.format` → `{}` placeholder
- 자주 만드는 임시 객체 → object pool (단, 잘못 쓰면 leak)
- `JsonNode` 매번 파싱 → cache

**Escape Analysis와 Scalar Replacement** — JIT가 객체가 메서드 밖으로 안 나가는 걸 알면 stack에 할당하거나 필드를 register로 분해. 무의식 중에 GC 부담 줄여줌. **lambda + 작은 메서드 + final** 패턴이 EA 친화적.

## 7.6 전략 5: Humongous Object 회피 (G1)

Region 크기의 절반 이상 객체 = humongous. 별도 region에 단독 할당, **GC 시 별도 처리** → pause 증가 원인.

**진단**:
```
GC 로그에서 "humongous regions" 카운트 확인
-Xlog:gc+humongous*
```

**조치**: 큰 byte[] / String 을 가능하면 chunk 분할. 또는 G1HeapRegionSize를 키워서 humongous 임계값 올림.

## 7.7 전략 6: Safepoint 진입 시간 단축

Pause = "**모든 스레드가 safepoint에 도달할 때까지** + **GC 작업**". GC 자체가 짧아도 **safepoint sync가 느리면** pause 길어짐.

**Safepoint 진단**:
```bash
-Xlog:safepoint*
```

**전형적 원인**:
- 큰 counted loop 안에서 safepoint poll 없는 코드 (JIT가 long counted loop에서 safepoint 생략 가능)
  → JDK 10+ `-XX:+UseCountedLoopSafepoints` 기본 활성화
- JNI 코드에서 오래 안 돌아옴
- monitor 경합으로 thread가 못 멈춤

## 7.8 운영 체크리스트

```
[GC pause 줄이기 진단 순서]
1. GC 로그 활성화: -Xlog:gc*,safepoint*
2. p99 측정: 어느 phase가 길어?
3. Phase 별 진단:
   - Initial mark 길다 → root 많음 (스레드 수, static 많음)
   - Concurrent mark 길다 → heap 크다, 객체 많다
   - Remark 길다 → SATB queue 처리 시간 (G1)
   - Compaction 길다 → 살아있는 객체 많음 (Old gen full)
4. 알고리즘 적합성: G1 → ZGC 전환 검토
5. Allocation rate 측정: async-profiler
6. Allocation hot spot 제거
```

## 7.9 시니어 한 줄

> "Pause를 줄이는 길은 두 갈래 — '**GC가 STW에서 하는 일을 줄이는 방향(ZGC 전환, region 작게, MaxGCPauseMillis 조정)**' 과 '**GC가 회수할 객체 자체를 줄이는 방향(allocation profiling, EA 친화적 코드, humongous 회피)**'. 후자가 항상 더 효과적이지만 코드 변경이 필요해서 어렵고, 전자는 옵션 한 줄로 즉시 효과지만 throughput 손실이 있다. **실무는 둘을 같이** 한다."

---

# 8. 컨테이너 환경의 JVM 메모리 (cgroup awareness)

> **한 줄 정의**: 컨테이너 안에서 JVM은 호스트의 메모리/CPU가 아닌 **cgroup limit**을 인식해야 OOMKilled를 피할 수 있고, JDK 10+의 **UseContainerSupport**가 기본 활성화되며, 운영에서는 **MaxRAMPercentage**로 비율 지정 + **non-heap 영역까지 합쳐 컨테이너 limit 안에 들어오게** 설계하는 게 핵심이다.

## 8.1 본질 — 왜 컨테이너에서 JVM이 죽었나 (역사)

**JDK 9 이전**의 문제:
```
[호스트 머신: 64GB RAM, 32 cores]
└── [컨테이너 A: limit 4GB, 2 cores]
       └── JVM:
           - Runtime.getRuntime().availableProcessors() → 32 ← 호스트 거 봄
           - 기본 -Xmx → 호스트 RAM의 1/4 = 16GB ← 호스트 거 봄
           - GC 스레드 수 → 32 코어 기준
       → -Xmx 16GB 시도 → 컨테이너 limit 4GB 초과 → OOMKilled
       → 또는 GC 스레드 32개 띄움 → 2 core에서 CPU throttling
```

JVM이 cgroup을 안 봤기 때문. K8s/Docker 운영에서 **가장 흔한 사고**였음.

## 8.2 UseContainerSupport (JDK 10+)

```bash
-XX:+UseContainerSupport   # 기본 활성화 (JDK 10+)
```

이제 JVM이 cgroup v1/v2 의 메모리/CPU limit 을 직접 인식:

```
[Container limit: memory=4GB, cpu=2]
JVM 내부:
  - Runtime.getRuntime().availableProcessors() → 2
  - 기본 MaxRAMPercentage = 25% → -Xmx ≈ 1GB
  - GC 스레드 수 → 2 코어 기준
```

**JDK 8u131+ 도 일부 지원** 하지만 불완전. JDK 11 LTS 이상에서 완전.

## 8.3 MaxRAMPercentage — 비율 기반 heap 지정

```bash
# 전통적: 절대값
-Xmx2g

# 컨테이너 친화: 비율
-XX:MaxRAMPercentage=75.0
-XX:InitialRAMPercentage=75.0    # = -Xms와 같은 효과
-XX:MinRAMPercentage=50.0        # 200MB 이하 컨테이너에만 적용
```

**왜 비율인가** — 동일 컨테이너 이미지를 다양한 limit으로 배포할 때 (dev=512MB, prod=8GB) 절대값은 매번 변경 필요. 비율은 자동 적응.

**75%의 의미** — 컨테이너 limit의 75%를 heap. 나머지 25%는:
- Metaspace
- Code Cache
- Thread stacks
- GC structures
- Direct buffers
- JVM internal

이 25%가 부족하면 OOMKilled. **75%는 일반적이지만 non-heap 사용량에 따라 조정**.

## 8.4 Non-heap 영역까지 계산하는 공식

```
컨테이너 limit ≥ -Xmx
              + MaxMetaspaceSize
              + ReservedCodeCacheSize
              + (Thread 수 × -Xss)
              + MaxDirectMemorySize
              + GC overhead (heap의 ~10-20%)
              + Native libs (Netty, JNI 등)
              + OS overhead (~50-100MB)
```

**예시 (4GB 컨테이너)**:
```
컨테이너 limit:           4096 MB
- Metaspace:               256 MB
- Code Cache:              512 MB
- Thread (200×1MB):        200 MB
- DirectMemory:            512 MB
- GC overhead (15%):       450 MB (heap 3000MB의 15%)
- Native + OS:             200 MB
─────────────────────────────────
Non-heap 합계:            2130 MB
가능 heap:                ~2000 MB → -Xmx2g 또는 MaxRAMPercentage=50
```

→ **MaxRAMPercentage=75는 위험할 수 있다**. 앱 특성에 맞춰 계산.

## 8.5 CPU limit과 GC 스레드

```bash
-XX:ActiveProcessorCount=N   # 명시 가능
```

UseContainerSupport는 CPU limit도 인식하지만, **cgroup cpu.cfs_quota / cpu.cfs_period** 비율로 계산하므로 fractional CPU (1.5 core 같은) 의 경우 반올림 동작이 헷갈릴 수 있음. **production은 명시가 안전**.

## 8.6 컨테이너 환경의 GC 선택

| Heap | CPU | 권장 |
|---|---|---|
| < 4GB | 2 core 이하 | G1 (기본) |
| 4~16GB | 4 core 이상 | G1 또는 ZGC |
| > 16GB | 8 core 이상 | ZGC (또는 Shenandoah) |
| 메모리 빠듯 | 어떤 CPU | Parallel (overhead 적음) |

**ZGC가 컨테이너에서 주의할 점** — ZGC는 RAM 대비 추가 메타데이터 사용량이 다른 GC보다 큼 (colored pointer 추적 등). 작은 컨테이너에선 비효율.

## 8.7 K8s 운영 베스트프랙티스

### Deployment 예시
```yaml
resources:
  requests:
    memory: "4Gi"
    cpu: "1"
  limits:
    memory: "4Gi"      # request = limit (QoS Guaranteed)
    cpu: "2"
env:
  - name: JAVA_OPTS
    value: >
      -XX:+UseG1GC
      -XX:MaxRAMPercentage=70.0
      -XX:InitialRAMPercentage=70.0
      -XX:MaxMetaspaceSize=256m
      -XX:ReservedCodeCacheSize=256m
      -XX:MaxDirectMemorySize=512m
      -XX:+ExitOnOutOfMemoryError
      -XX:+HeapDumpOnOutOfMemoryError
      -XX:HeapDumpPath=/dumps/
      -Xlog:gc*:file=/logs/gc.log:time,uptime:filecount=5,filesize=10M
```

### 모니터링 지표 (Prometheus + Micrometer)
```
필수:
- jvm_memory_used_bytes{area="heap"}        / max  → heap 사용률
- jvm_memory_used_bytes{area="nonheap"}     / max  → Metaspace 등
- jvm_gc_pause_seconds{action="..."}              → GC pause 분포
- container_memory_working_set_bytes              → cgroup 측정 RSS
- container_memory_working_set_bytes / limit      → 컨테이너 사용률
```

**알람 룰**:
- container_memory_working_set / limit > 0.9 for 5min → OOMKilled 임박
- jvm_gc_pause_seconds_max > 0.5 → pause 비정상
- non-heap이 단조 증가 → Metaspace/ClassLoader leak

## 8.8 OOMKilled 진단 흐름 (컨테이너)

```
1. kubectl describe pod → Last State: Terminated, Reason: OOMKilled
2. 컨테이너 메모리 그래프 확인 (Grafana)
   - 급증인가? 단조 증가인가?
   - 급증 → Direct buffer / 큰 allocation
   - 단조 증가 → leak
3. heap dump 확인 (-XX:+HeapDumpOnOutOfMemoryError 가 작동했나?)
   - heap이 -Xmx 안 채우고 OOMKilled → non-heap 문제
4. NMT diff (있다면) → 어느 카테고리가 자라는지
5. 진단별 조치:
   - heap이 찼다 → -Xmx 부족 또는 코드 leak
   - Metaspace가 찼다 → ClassLoader leak
   - Thread가 많다 → ExecutorService leak
   - Direct가 많다 → Netty / NIO leak
```

## 8.9 함정 정리

| 함정 | 증상 | 회피 |
|---|---|---|
| -Xmx만 지정, non-heap 무시 | OOMKilled (heap dump 깨끗) | 위 공식대로 계산 |
| UseContainerSupport 없는 옛 JVM | availableProcessors 32 반환 | JDK 11+ 사용 |
| MaxRAMPercentage=75 무비판 적용 | 4GB 컨테이너에서 OOMKilled | 앱별 계산 |
| HeapDumpOnOOM 경로가 ephemeral | dump 파일 잃음 | PVC mount |
| K8s memory limit < request | swap 없는 환경에서 즉시 OOMKilled | request = limit |
| GC 스레드가 CPU limit 초과 | CPU throttling, latency 폭증 | ParallelGCThreads 명시 |

## 8.10 시니어 한 줄

> "컨테이너에서 JVM은 '**heap 외에 Metaspace, Code Cache, Thread stack, Direct buffer, GC overhead까지 모두 cgroup limit 안에 들어와야 한다**'. JDK 11+에서 UseContainerSupport가 기본이지만, 그것만 믿으면 안 되고 MaxRAMPercentage + 각 non-heap 영역 명시까지 해야 OOMKilled를 피한다. 진단은 **container_memory_working_set_bytes** 그래프 + heap dump + NMT diff 3종 세트."

---

# 종합 — 한 줄씩 정리

| # | 주제 | 시니어 한 줄 |
|---|---|---|
| 1 | JVM 메모리 구조 | Heap과 Metaspace만 GC 대상. OOM은 영역별로 진단 경로가 완전히 다르다. |
| 2 | Young/Old | Young=Copy로 빠르게, Old=Mark-Compact로 가끔 길게. 80% 이슈는 Premature Promotion. |
| 3 | G1/CMS/ZGC | concurrent 정확성 보장 진화 — SATB write barrier → ZGC load barrier로 pause를 sub-ms까지. |
| 4 | 튜닝 | 모든 영역 상한 명시. -Xms=-Xmx + MaxMetaspaceSize + ReservedCodeCacheSize + MaxDirectMemorySize. |
| 5 | 메모리 릭 | "의도하지 않은 strong ref가 GC root에". 4대 패턴(ThreadLocal/static/ClassLoader/Listener) + MAT Dominator Tree. |
| 6 | NMT | 컨테이너 OOMKilled에 heap dump가 깨끗하면 답은 NMT. baseline→summary→diff. |
| 7 | Pause 줄이기 | GC가 하는 일을 줄이거나(ZGC) allocation 자체를 줄이거나. 둘 다 한다. |
| 8 | 컨테이너 | heap 외 영역까지 cgroup limit 안에 들어와야. MaxRAMPercentage + non-heap 명시 + container_memory_working_set 모니터. |

## 면접에서 8문항 줄줄 답하기 위한 마인드맵

```
                          [JVM Memory + GC]
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
    [구조 축]                [GC 알고리즘 축]            [운영 축]
        │                        │                        │
   5개 영역 (Q1)              세대 분리 (Q2)            튜닝 (Q4)
        │                        │                        │
   Stack/PC/Native          Eden/Survivor              -Xms=-Xmx
   (auto)                   Promotion                   MaxMetaspaceSize
                            Card Table                  ReservedCodeCacheSize
   Heap/Metaspace                │                       │
   (GC 대상)                G1/CMS/ZGC (Q3)           메모리 릭 진단 (Q5)
                            RSet, SATB                  ThreadLocal
                            Colored ptr                 static Map
                            Load barrier                ClassLoader
                                  │                     Listener
                            Pause 줄이기 (Q7)             │
                            ZGC 전환                  NMT (Q6)
                            allocation 줄이기            컨테이너 (Q8)
                                                       UseContainerSupport
                                                       MaxRAMPercentage
```

**최종 시니어 메시지** —

> "JVM 메모리와 GC는 **'각 영역의 lifetime이 다르다'** 는 본질에서 시작해서, **'concurrent 작업의 정확성을 어떻게 보장하나'** 는 알고리즘 진화로 이어지고, **'컨테이너 limit 안에 모든 영역이 들어와야 한다'** 는 운영 제약으로 끝난다. 면접관이 어디서 시작해도 이 3축 안에서 풀어내면 된다."
