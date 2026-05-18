# 02-01. Heap & TLAB — 객체가 살고 죽는 곳

> JVM에서 `new`를 호출하면 객체가 **어디에, 어떤 알고리즘으로** 할당되는가?
> 답: **Eden의 TLAB 안에서 bump-the-pointer로 3 instruction**.
> 이게 Java가 C++ `new`보다 빠른 이유 — 그리고 GC가 일을 더 해야 하는 이유.

---

## 📍 학습 목표

이 챕터가 끝나면 다음을 모두 답할 수 있다.

1. Heap의 세대 구분 (Young/Old)을 그릴 수 있고, Young 안의 Eden/S0/S1 비율을 안다.
2. TLAB(Thread-Local Allocation Buffer)이 무엇이고, 왜 lock 없이 할당 가능한지 안다.
3. TLAB이 가득 차면 일어나는 두 가지 경로 (retire & new TLAB vs slow path)를 안다.
4. Humongous Object의 정의 (region 크기의 50% 이상)와 운영 함정을 안다.
5. Object Header 구조 (Mark Word + Klass Pointer)를 안다 — Biased Lock부터 GC mark까지의 정보가 다 여기.
6. Compressed Oops가 무엇이고 32GB 이하 Heap에서만 활성화되는 이유를 안다.
7. -Xmx, -Xms, -XX:NewRatio, -XX:SurvivorRatio, -XX:MaxTenuringThreshold의 의미와 영향.
8. JFR `jdk.ObjectAllocationInNewTLAB` / `jdk.ObjectAllocationOutsideTLAB` 이벤트로 할당 패턴 분석.

---

## 🎨 1단계: 백지 그리기 가이드

### Step 1: 가장 바깥 박스 — Heap (Java Heap)
- 큰 사각형 그리고 우상단에 "Java Heap (`-Xmx`로 제어)"
- 박스 좌측에 "모든 스레드 공유" 표시

### Step 2: Heap을 좌우로 분할
- **좌측 40%** — Young Generation (밝은 노란색)
- **우측 60%** — Old Generation (Tenured, 진한 색)
- 좌측 라벨: "새 객체 — Minor GC 자주"
- 우측 라벨: "오래된 객체 — Major/Full GC"

### Step 3: Young을 다시 3분할 (좌측에서)
- **Eden** (80%) — 새 객체 할당
- **S0** (10%) — Survivor 0
- **S1** (10%) — Survivor 1
- 화살표: Eden → S0/S1 (살아남으면) → 반대 S로 (다음 GC에) → 충분히 살면 Old로 (Promotion)

### Step 4: Eden 안에 TLAB 그리기
- Eden 안에 작은 세로 띠들로 표시: TLAB-Thread1, TLAB-Thread2, ...
- 각 TLAB 안에 화살표: `start | filled |--→ top |---unused---| end`
- 라벨: "bump-the-pointer 할당 — lock-free"

### Step 5: 큰 객체 영역 (G1만 해당)
- Old 영역 안에 별도 박스로 "Humongous Region (≥ region size × 50%)"
- 주석: "G1: region 단위 (1~32MB), Humongous는 region 통째 차지"

### Step 6: Object Header 줌인
- 우측에 객체 하나를 줌인해서 그림
- `[Mark Word (8B) | Klass Ptr (4B compressed / 8B) | Fields...]`
- Mark Word 안에 비트맵: hash | age | biased | lock state

### 정답 그림

> 이 챕터의 SVG는 다음 턴에 생성. 우선 ASCII로 시각화:

```
Java Heap (-Xmx로 제어)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Young Generation (40%, default)            Old Generation (60%)
  ┌─────────────────────────────────┐       ┌─────────────────────────┐
  │ Eden (80% of Young)              │       │ Tenured                  │
  │  ┌─────┐┌─────┐┌─────┐┌─────┐    │ ──→  │                          │
  │  │TLAB1││TLAB2││TLAB3││ ... │    │ promo│  오래 살아남은 객체        │
  │  │ T₁  ││ T₂  ││ T₃  ││ Tₙ  │    │      │  (Tenuring Threshold)    │
  │  └─────┘└─────┘└─────┘└─────┘    │      │                          │
  └──────┬──────────────────────────┘       │  [Humongous Region]      │
         │ Minor GC                          │   (≥ region size × 50%, │
         ▼ 살아남은 객체                       │    G1만 해당)            │
  ┌──────────────┐  ┌──────────────┐         │                          │
  │ S0 (10%)     │←→│ S1 (10%)     │         └─────────────────────────┘
  │ Survivor 0   │  │ Survivor 1   │
  └──────────────┘  └──────────────┘
        ↑ ↓ Copy GC: 살아있는 객체를 S0 ↔ S1로 옮김
          매번 age + 1, threshold 도달 시 Old로 promote
```

---

## 🧠 2단계: 직관

### 핵심 비유

> **호텔 비유**:
> - **Eden** = 로비. 모든 신규 투숙객이 처음 들어옴. 회전율 매우 높음.
> - **Survivor (S0/S1)** = 임시 객실. 며칠 더 머물 사람들. 정기적으로 청소(Minor GC).
> - **Tenured (Old)** = 장기 투숙 객실. 충분히 머물러 옮긴 사람들. 청소 드물지만 큰 일.
> - **TLAB** = 각 직원이 미리 받아둔 객실 키 묶음. 손님 올 때마다 본부에 요청 안 하고 자기 묶음에서 바로 줌. (lock-free)
> - **Humongous** = 단체 투숙객 — 한 객실에 못 들어가는 큰 짐. 별도 큰 객실 통째로 줘야 함.

### 정확한 정의 (비유와 분리)

| 용어 | 정의 |
|---|---|
| **Heap** | JVM이 객체 인스턴스를 할당하는 메모리 영역. `-Xmx`로 최대 크기 지정. 모든 스레드 공유. |
| **Young Generation** | 새 객체가 할당되는 곳. Minor GC의 대상. Eden + S0 + S1로 구성. |
| **Old Generation (Tenured)** | Young에서 충분히 살아남은 객체가 이동하는 곳. Major/Full GC의 대상. |
| **Eden** | Young 안에서 실제 신규 할당이 일어나는 영역. 기본적으로 Young의 80%. |
| **Survivor (S0/S1)** | Minor GC에서 살아남은 객체를 임시 보관. 두 영역이 ping-pong 방식으로 동작. |
| **TLAB (Thread-Local Allocation Buffer)** | Eden 안에서 각 스레드가 점유한 작은 영역. lock 없이 bump-the-pointer 할당. |
| **Humongous Object** | (G1 전용) Region 크기의 50% 이상인 큰 객체. Old gen에 직접 할당. |
| **Promotion** | Young → Old로 객체 이동. 일정 age 또는 Survivor 부족 시. |
| **Tenuring** | Promotion의 다른 표현. age 카운터 기반 결정. |

### 왜 세대(Generation)로 나눴나 — Weak Generational Hypothesis

> **약한 세대 가설**: "대부분의 객체는 일찍 죽는다."
>
> 실측 데이터: Java 앱 객체의 **80~98%가 첫 GC를 못 넘긴다**.
> → Young을 자주 청소하면 작업량 적음 (살아있는 객체가 적으니 copy 비용 작음).
> → Old는 가끔만 청소 (대부분 살아있으므로 효율 낮음).

이 가설이 모든 generational GC의 기반. 이게 통하는 워크로드(웹 서버, 마이크로서비스)에서 매우 효율적.

### 왜 Young은 Copying, Old는 Mark-Sweep인가 — "청소"의 두 철학

> **이사 비유**:
> - **Mark-Sweep (Old gen 방식)**: 방 안을 돌아다니며 쓰레기를 **하나하나 찾아 버린다**. 살아있는 물건은 그대로 두고. → 비용 ∝ 쓰레기 수.
> - **Copying (Young gen 방식)**: 살릴 물건 몇 개만 **새 방으로 들고 나간다**. 원래 방? **통째로 폭파**. 안에 뭐가 있었는지 신경 안 씀. → 비용 ∝ 살릴 물건 수.

세대별로 알고리즘이 다른 이유:

| | Young (살아있는 게 1~20%) | Old (살아있는 게 80~95%) |
|---|---|---|
| 죽은 객체 비율 | 매우 높음 (80~99%) | 낮음 (5~20%) |
| Copying 쓰면? | 죽은 다수를 **아예 안 만짐** → 압도적 효율 | 살아있는 다수를 거의 다 복사 → 비효율 |
| Mark-Sweep 쓰면? | 죽은 다수를 일일이 free list 등록 → 낭비 | 살아있는 건 그대로, 죽은 것만 처리 → 효율 |
| 선택 | **Copying** | **Mark-Sweep (+ Compact)** |

**핵심 반전 — Copying GC는 죽은 객체를 "지우지" 않는다**:

```
Copying GC의 동작:
  1. 살아있는 소수를 다른 영역(S0↔S1)으로 옮긴다
  2. 원래 영역(Eden)은 "없는 셈" 친다 — top 포인터를 start로 되돌림
  3. 죽은 객체의 비트는 그대로 남아있음
  4. 다음 new 호출 시 그 위에 덮어써질 뿐

→ 죽은 객체에 대해 GC가 한 일 = 0. 만지지도 않음.
```

> "청소를 잘하는 것"이 아니라 "**청소 안 해도 되게 만드는 것**"이 Copying의 본질.
> 살아있는 소수만 안전한 곳으로 대피시킨 다음, 원래 영역은 통째로 리셋.

**대신 단점**: 메모리를 2배 써야 함 (복사 대상 공간 S0/S1 필요). 하지만 Young만 작게 잡으면 부담 적음 — 그래서 Survivor 영역은 Young의 10%씩만.

### 왜 TLAB가 필요한가 — 동시 할당 충돌 회피

```
TLAB 없이 (가상):                  TLAB 있음 (실제 HotSpot):
━━━━━━━━━━━━━━━━━                  ━━━━━━━━━━━━━━━━━━━━━━

Thread 1: new Foo()                Thread 1: new Foo()
  └→ Eden.top 변경 (락 필요!)         └→ TLAB1.top += sizeof(Foo)
Thread 2: new Bar()                       (lock-free, 3 instruction)
  └→ Eden.top 대기 (contention)
Thread 3: ...                       Thread 2: new Bar()
                                      └→ TLAB2.top += sizeof(Bar)
                                          (Thread 1과 완전 독립)
━━━━━━━━━━━━━━━━━                  ━━━━━━━━━━━━━━━━━━━━━━
N개 스레드 → 직렬화                 N개 스레드 → 완전 병렬
```

→ 멀티코어에서 객체 할당의 lock-free scalability를 제공.

---

## 🔬 3단계: 구조

### Heap 전체 — 시대별 변화

```
[JDK 7까지]                               [JDK 8+]
━━━━━━━━━━━                                ━━━━━━━━━━━
Heap                                       Heap
├── Young                                  ├── Young
│   ├── Eden                               │   ├── Eden
│   ├── Survivor 0                         │   ├── Survivor 0
│   └── Survivor 1                         │   └── Survivor 1
├── Old (Tenured)                          ├── Old (Tenured)
└── PermGen ★                              └── (PermGen 사라짐)
   (Heap 안의 별도 generation)
   - Class 메타데이터
   - interned String           → JDK 7부터 String Pool은 Heap의 일반 영역으로
   - static 필드                  JDK 8부터 Class 메타데이터는 Metaspace(native)로
```

### Young Gen 내부 (Eden + Survivor)

```
Young Generation 100%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
│←──────────  80%  ──────────→│←─ 10% ─→│←─ 10% ─→│
│             Eden              │   S0    │   S1    │
│  (신규 할당, TLAB들이 여기)    │ (active)│ (empty) │
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                                  ↑          ↑
                                  Minor GC마다 active 토글
                                  (S0 → S1 또는 S1 → S0)
```

비율 제어:
- `-XX:NewRatio=2` → Old : Young = 2 : 1 (Young은 전체의 1/3)
- `-XX:SurvivorRatio=8` → Eden : S0 : S1 = 8 : 1 : 1
- `-XX:NewSize`, `-XX:MaxNewSize` — Young 크기 직접 지정

### Minor GC 흐름 (Copying Algorithm) — 단계별 추적

```
[GC 직전]
Eden:  [A][B][C][D][E][F][G][H]      ← 8개 중 B, E만 살아있음 (참조됨)
                                       나머지 A,C,D,F,G,H는 dead (참조 없음)
S0:    [X][Y]                          ← 이전 GC에서 옮겨온 살아있는 애들 (active)
S1:    [              ]                ← 비어있음 (대기조)
Old:   ████████                        ← 일부 사용

       │ Minor GC 시작 (STW)
       ▼

[Step 1] Root에서 출발해 "살아있는 객체"만 추적 (Mark)
         - GC Root (스택 로컬, static 필드, JNI 참조 등)에서 reachable 추적
         - Eden의 B, E / S0의 X, Y 가 살아있다고 판정
         - 나머지(A,C,D,F,G,H)는 추적조차 안 함 ★ 죽은 객체는 비용 0

[Step 2] 살아있는 애들을 S1에 복사 (Copy)
         - 새 주소에 복사본 생성, 모든 참조도 새 주소로 갱신
         - age 카운터 +1
         - age > MaxTenuringThreshold 면 S1 대신 Old로 promote
S1:    [B'][E'][X'][Y']

[Step 3] Eden과 S0를 통째로 "버림" (Reclaim)
         - 죽은 객체 A,C,D,F,G,H는 명시적으로 지우지 않음 ★
         - top 포인터를 start로 되돌리는 것만으로 "빈 공간" 선언
         - 다음 new 호출 시 죽은 객체 비트 위에 그대로 덮어써짐

       │ STW 끝, 사용자 코드 재개
       ▼

[GC 직후]
Eden:  [                      ]       ← top = start, 즉시 재사용 가능
S0:    [                      ]       ← 비움
S1:    [B'][E'][X'][Y']               ← 다음 GC까지 active
Old:   ████████◇◇                     ← promote된 객체 추가

→ 다음 Minor GC 때는 Eden + S1 → S0로 복사. S0/S1이 ping-pong으로 active 토글.
```

**핵심 정리**:

| | Mark-Sweep (Old) | Copying (Young) |
|---|---|---|
| 죽은 객체 처리 | 하나하나 찾아 free list 등록 | **무시. 덮어써질 때 자연 소멸** |
| 살아있는 객체 처리 | 원래 자리에 그대로 | **다른 영역으로 복사** |
| 영역 재사용 | 죽은 자리만 부분적 (단편화 발생) | **영역 전체 통째 재사용** (단편화 0) |
| 비용 기준 | 전체 객체 수 | 살아있는 객체 수 |
| 추가 이점 | — | Compaction 자동 + 다음 할당이 bump-the-pointer로 가능 |

→ Young GC가 빠른 이유: **살아있는 객체가 적으니 copy 비용 작고, 죽은 객체는 만지지도 않음**.
→ Eden을 통째로 비울 수 있는 이유: 살아있는 애들을 S0/S1로 대피시켰으므로 원래 영역에 미련 없음.

### TLAB 내부 구조

```
TLAB (스레드별, Eden 안에 위치)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  start                                              end
   ▼                                                  ▼
   ┌─────────────────────┬───────────────────────────┐
   │ 이미 할당된 객체들    │      미사용 (free)         │
   │ (Foo, Bar, Baz, ...)│                            │
   └─────────────────────┴───────────────────────────┘
                          ▲
                          top (bump pointer)

크기: 기본 ~64KB ~ 1MB 사이 (JVM이 동적 조정)
제어: -XX:TLABSize, -XX:ResizeTLAB (기본 on)
```

### bump-the-pointer 할당 코드 (HotSpot)

위치: `src/hotspot/share/gc/shared/threadLocalAllocBuffer.hpp`

```cpp
class ThreadLocalAllocBuffer {
private:
  HeapWord* _start;     // TLAB 시작 주소
  HeapWord* _top;       // 다음 할당 위치 (★ bump pointer)
  HeapWord* _end;       // TLAB 끝

public:
  HeapWord* allocate(size_t size) {
    HeapWord* obj = _top;
    HeapWord* new_top = _top + size;
    if (new_top <= _end) {
      _top = new_top;     // ★ 단 한 줄로 할당 완료
      return obj;          // ★ lock 없음, single thread context
    }
    return NULL;          // TLAB full, slow path로
  }
};
```

→ **정상 케이스 3 instruction (load, add, compare-and-branch)**. 이게 Java의 객체 할당이 빠른 이유.

### TLAB이 가득 찼을 때 — 두 가지 경로

```
TLAB.allocate(size) 실패 (new_top > _end)
                │
                ▼
        남은 공간이 큰가?
                │
        ┌───────┴───────┐
        ▼               ▼
  남은 공간 크면         남은 공간 작으면
        │               │
        ▼               ▼
  [경로 A]              [경로 B]
  Eden 직접 할당         TLAB Retire & 새 TLAB
  (Slow Path)           (Refill)
        │                │
   해당 객체만             남은 공간을 filler object로 채움
   Eden의 다른            (Heap walking을 위한 일관성)
   영역에 할당             그리고 새 TLAB을 Eden에서 받아옴
        │                │
        └───────┬────────┘
                ▼
          할당 완료
```

**filler object의 정체**: TLAB의 남은 자투리를 그냥 두면 GC가 Heap walking할 때 "여기 무슨 객체가 있나" 혼란. 더미 `int[]` 같은 객체로 채워 명시적으로 dead 처리.

위치: `src/hotspot/share/gc/shared/collectedHeap.cpp`의 `fill_with_object`.

### Eden full → Minor GC 트리거

```
Eden.allocate(size) 실패 (TLAB도 새로 못 받음)
                │
                ▼
         Minor GC 트리거
                │
                ▼
  STW(Stop-The-World) 시작
                │
                ▼
  Young Gen scan + Copy live objects
                │
                ▼
  Eden 비우기 + Survivor toggle + 일부 Old promote
                │
                ▼
  STW 끝, 사용자 코드 재개
                │
                ▼
  실패했던 allocate() 재시도 → 성공
```

빈도: 부하 상황의 일반적 Java 앱에서 **수 초마다 한 번**. STW 시간: 일반적으로 **10~50ms**.

### Promotion / Tenuring

```
각 객체에는 age 카운터가 Object Header에 있음 (4비트)

객체 생성: age = 0
Minor GC 1번 살아남음: age = 1
Minor GC 2번 살아남음: age = 2
...
age > MaxTenuringThreshold (기본 15) 또는
Survivor 공간 부족 → Old로 promote (★ Tenuring)
```

**Tenuring Threshold가 동적인 이유**:
- JVM이 Survivor 사용량을 보고 threshold를 동적 조정.
- Survivor가 자주 차면 threshold 낮춤 (더 빨리 promote).
- 너무 자주 promote하면 Old 압박 → Full GC 위험.

### Humongous Object (G1 전용)

G1은 Heap을 **region**(1~32MB)으로 나눔. 일반 객체는 region 안에 들어가지만:

```
Region 크기 = 4MB (기본 자동 조정)
            ━━━━━━━━━━━━━━━━━━━━━

   일반 객체: ≤ 2MB           Humongous: > 2MB (region의 50%)
   ┌─────────────────┐         ┌─────────────────┐
   │ Region 안에      │         │ Region 통째     │
   │ 여러 개 들어감    │         │ 차지            │
   │ ●●●●●           │         │ ████            │
   └─────────────────┘         └─────────────────┘
                               + 연속된 추가 region도
                                 필요시 점유
```

**문제점**:
1. **Old gen 직접 할당**: Young GC를 건너뜀 → 일찍 죽어도 회수 늦음.
2. **Fragmentation**: Humongous region이 흩어져 있으면 큰 객체 신규 할당 어려움.
3. **연속 region 점유**: 4MB region에 5MB 객체면 region 2개 통째 점유 (1개는 일부만 사용 — 낭비).

진단:
```bash
-Xlog:gc+humongous=debug
# 또는 JFR: jdk.G1HeapRegionTypeChange 이벤트
```

회피: 가능하면 큰 배열을 startup에 한 번만 할당 (재사용), `-XX:G1HeapRegionSize`로 region 크기 조정.

### Object Header — 객체의 신분증

```
객체 메모리 레이아웃 (HotSpot 64-bit, Compressed Oops 활성):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

┌──────────────────┬──────────────┬──────────────────┐
│ Mark Word (8B)    │ Klass Ptr(4B)│ Fields ...       │
└──────────────────┴──────────────┴──────────────────┘
   ↓ Mark Word 내부 (state에 따라 다름):

Unlocked:    [unused:25 | hash:31 | unused:1 | age:4 | biased:1 | lock:2]
Biased:      [thread:54 | epoch:2 | unused:1 | age:4 | biased:1 | lock:2]
Lightweight: [ptr to lock record:62                              | lock:2]
Heavyweight: [ptr to monitor:62                                  | lock:2]
GC marked:   [forwarding pointer (or marked bit)                          ]
```

**Klass Pointer**: 객체의 클래스 정보(`InstanceKlass*`)를 가리킴. Metaspace의 클래스 객체 참조.
**Compressed Oops**: 64-bit 시스템에서 32-bit 포인터로 압축 → 메모리 절감 (대신 Heap 32GB 제한).

### Compressed Oops — 32-bit 포인터의 부활

```
일반 64-bit oop:    [────────── 8 bytes ──────────]  (모든 객체 ref가 8B)

Compressed oop:     [── 4 bytes ──]                  (모든 객체 ref가 4B)
                    실제 주소 = base + (compressed_oop << 3)
                                                ↑ shift 3 = 8바이트 정렬
```

- **활성 조건**: Heap < 32GB (정확히는 압축 가능한 최대 크기).
- **JVM이 자동 결정**: `-XX:+UseCompressedOops` (기본 on, JDK 6u23+).
- **장점**: 메모리 사용량 ~30% 감소, 캐시 효율 향상.
- **단점**: 압축/복원 명령 추가 (shift 연산), 32GB 이상 Heap에서 자동 비활성.

→ "**32GB의 벽**" — Heap을 32GB 이상으로 키우면 갑자기 메모리 사용량이 늘어남. 31GB에서 안 죽으면 31GB가 가장 효율적.

---

## 🧬 4단계: 내부 구현 — HotSpot

### Heap 초기화

위치: `src/hotspot/share/gc/shared/genCollectedHeap.cpp` (Parallel/Serial 기준)
또는 `src/hotspot/share/gc/g1/g1CollectedHeap.cpp` (G1)

```cpp
// g1CollectedHeap.cpp (요약)
jint G1CollectedHeap::initialize() {
  // 1. -Xmx, -Xms 등 옵션 반영
  size_t init_byte_size = collector_policy()->initial_heap_byte_size();
  size_t max_byte_size = collector_policy()->max_heap_byte_size();

  // 2. 가상 메모리 reserve (mmap, 아직 실제 메모리 사용 아님)
  ReservedSpace heap_rs = Universe::reserve_heap(max_byte_size, ...);

  // 3. Region 배열 초기화
  _hrm.initialize(...);

  // 4. Card Table 등 GC 자료구조 초기화
  _card_table = new G1CardTable(...);

  // 5. 초기 Young Gen 크기 결정
  _eden = ...;
  return JNI_OK;
}
```

### TLAB 할당 — 사용자 코드 진입점

위치: `src/hotspot/share/gc/shared/memAllocator.cpp`

```cpp
// memAllocator.cpp (의사 코드)
HeapWord* MemAllocator::allocate() {
  // 1. Fast path: 현재 스레드의 TLAB에서 시도
  HeapWord* mem = _thread->tlab().allocate(_word_size);
  if (mem != NULL) return mem;  // ★ 99% 케이스

  // 2. Slow path: TLAB 가득 또는 너무 작음
  return allocate_outside_tlab();
}

HeapWord* MemAllocator::allocate_outside_tlab() {
  // TLAB이 남은 공간이 충분히 크면 새 TLAB 받기 시도
  if (should_refill_tlab()) {
    // 옛 TLAB을 filler object로 채워 retire
    _thread->retire_tlab();
    // 새 TLAB을 Eden에서 받아옴
    HeapWord* new_tlab = allocate_new_tlab(...);
    return _thread->tlab().allocate(_word_size);
  }
  // 아니면 Eden에 직접 할당 (slow path)
  return _heap->mem_allocate(...);
}
```

### Promotion 결정

위치: `src/hotspot/share/gc/shared/ageTable.cpp`

```cpp
// ageTable.cpp
uint AgeTable::compute_tenuring_threshold(size_t survivor_capacity) {
  // 1. 각 age별로 차지하는 메모리 누적
  size_t total = 0;
  uint threshold = MaxTenuringThreshold;

  for (uint age = 1; age <= MaxTenuringThreshold; age++) {
    total += sizes[age];
    if (total * 2 > survivor_capacity * TargetSurvivorRatio / 100) {
      threshold = age;  // ★ Survivor 절반을 채우는 age를 threshold로
      break;
    }
  }
  return threshold;
}
```

→ 동적 threshold: Survivor 공간을 적절히 차도록 조정.

### Humongous Object 판정 (G1)

위치: `src/hotspot/share/gc/g1/g1CollectedHeap.cpp`

```cpp
// g1CollectedHeap.cpp
bool G1CollectedHeap::is_humongous(size_t word_size) const {
  // word_size: 객체가 차지할 워드 수
  // HeapRegion::GrainBytes: region 크기 (예: 4MB)
  return word_size >= humongous_threshold_for(HeapRegion::GrainBytes);
}

size_t G1CollectedHeap::humongous_threshold_for(size_t region_size) {
  return region_size / 2;  // ★ region의 절반 이상이면 humongous
}
```

---

## 📜 5단계: 역사 — Heap 진화

| 연도 | 릴리스 | 변화 | 이유 |
|---|---|---|---|
| 1996 | JDK 1.0 | Serial GC, generational Heap | 멀티코어 시대 전 |
| 2002 | JDK 1.4 | Parallel GC | Young Gen 병렬 수집, 멀티코어 활용 |
| 2002 | JDK 1.4 | CMS GC | 응답 시간 중시 워크로드 |
| 2009 | JDK 6u14 | Compressed Oops 도입 | 64-bit 메모리 효율 ↑ |
| 2012 | JDK 7u4 | G1 GC (실험) | "Garbage-First" — region 기반 |
| 2014 | JDK 8 | **PermGen 제거 → Metaspace** | OOM:PermGen 빈발, 동적 클래스 생성 대응 |
| 2014 | JDK 8 | **String Pool → Heap의 일반 영역** | PermGen 정리 일환, 일반 GC 대상 |
| 2017 | JDK 9 | **G1을 default GC**로 (Parallel 대체) | Latency 중시 추세 |
| 2018 | JDK 11 | ZGC 실험 | Heap 16TB까지, sub-ms pause |
| 2020 | JDK 14 | **CMS 제거** | Concurrent Mode Failure 문제 + G1 완성 |
| 2020 | JDK 15 | ZGC production-ready | |
| 2023 | JDK 21 | **Generational ZGC** | Weak generational hypothesis를 ZGC도 활용 |

### PermGen → Metaspace의 진짜 이유

옛 PermGen의 문제:
1. **크기 고정**: `-XX:MaxPermSize=256m` 으로 미리 잡아야 함 → 동적 클래스 생성 많은 앱(Spring AOP, Hibernate proxy, Mockito)에서 `OutOfMemoryError: PermGen space` 빈발.
2. **GC 비효율**: Heap 안의 generation이라 일반 GC 정책에 끼어들고, ClassLoader unload가 비효율.
3. **Compressed Oops 충돌**: Klass 포인터 압축에 PermGen 위치가 제약.

JDK 8에서:
- **Metaspace**: Heap 밖 native 메모리. 기본 무제한.
- **String Pool**: Heap의 일반 영역으로 이동 → 일반 GC가 처리.
- **Compressed Class Space**: Klass 포인터 압축용 별도 영역.

---

## ⚖️ 6단계: 트레이드오프 — 옵션과 GC별 비교

### Heap 크기 결정의 트레이드오프

| `-Xmx` 작게 | `-Xmx` 크게 |
|---|---|
| ✅ Footprint 작음 | ❌ Footprint 큼 |
| ✅ 컨테이너 친화 | ❌ Container limit 압박 |
| ❌ Full GC 자주 | ✅ Full GC 드물게 |
| ❌ OOM 위험 | ✅ Burst 견딤 |
| ❌ GC throughput ↓ | ✅ GC throughput ↑ |

**경험칙**:
- Container limit의 50~70%.
- 32GB는 절대 안 넘김 (Compressed Oops 비활성).
- `-Xms = -Xmx` (동적 resize는 hiccup 유발).

### NewRatio (Young vs Old 비율) 트레이드오프

| Young 크게 (NewRatio 작게) | Young 작게 (NewRatio 크게) |
|---|---|
| ✅ Minor GC 드물게 | ❌ Minor GC 자주 |
| ❌ Minor GC 한 번에 길게 | ✅ Minor GC 짧게 |
| ❌ Premature promotion (Survivor 부족) | ✅ Survivor 충분 |
| 일반적 워크로드 ✅ | 단명 객체 많은 워크로드 ✅ |

### Generational GC가 항상 답인가?

| 워크로드 | Generational | Non-Generational |
|---|---|---|
| 일반 웹 서버 (객체 대부분 짧게 산다) | ★ 매우 효율 | △ 비효율 |
| 분석 작업 (대용량 객체 오래 산다) | △ Old 압박 | ★ 효율 |
| 캐시 서버 (객체 절반 영구 보존) | △ Survivor 빨리 가득 | ★ 효율 |

→ 그래서 ZGC가 JDK 21까지 single-gen이었음 (모든 시나리오 균등). JDK 21 Generational ZGC로 양쪽 다 노림.

### TLAB 크기 트레이드오프

| TLAB 크게 | TLAB 작게 |
|---|---|
| ✅ Eden 직접 할당 (slow path) 적음 | ❌ Slow path 자주 |
| ❌ Eden 단편화 | ✅ Eden 효율적 |
| ❌ 적은 스레드일 때 Eden 낭비 | ✅ 많은 스레드 효율 |
| ❌ 큰 객체 할당 시 retire 손실 | ✅ |

`-XX:TLABSize` 직접 지정보다 `-XX:ResizeTLAB` (기본 on)로 JVM이 자동 조정하게 하는 게 일반적으로 최선.

### G1 region 크기 트레이드오프

| Region 크게 (32MB) | Region 작게 (1MB) |
|---|---|
| ✅ 적은 region 수 → GC 자료구조 작음 | ❌ region 수 많음 → RSet 비대 |
| ❌ Humongous threshold 크게 (16MB) | ✅ 작은 객체도 humongous (1MB) — 문제 |
| ❌ 한 region GC 비용 큼 | ✅ 미세한 GC |

Heap 크기 / 2048개 region이 일반적 가이드라인.

---

## 📊 7단계: 측정·진단

### Heap 사용 실시간 모니터링

```bash
# 1초 간격 GC 통계
jstat -gc <pid> 1s

# 출력:
# S0C    S1C    S0U    S1U      EC       EU        OC         OU       MC     MU
# 8704.0 8704.0 0.0    8639.5   69952.0  4096.0    175104.0   30192.0  ...
```

판독:
- `EC/EU` — Eden Capacity / Used
- `S0C/S0U` — Survivor 0
- `OC/OU` — Old
- `YGC` — Young GC 횟수
- `YGCT` — Young GC 누적 시간

### Heap dump (사후 분석)

```bash
# heap dump 생성
jcmd <pid> GC.heap_dump /tmp/heap.hprof

# OOM 시 자동 dump
java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/tmp/ -jar app.jar

# 분석: Eclipse MAT 또는 VisualVM
```

### TLAB 사용 패턴 (JFR)

```bash
# JFR 시작
jcmd <pid> JFR.start name=tlab settings=profile duration=60s filename=tlab.jfr

# 분석 (JDK Mission Control 또는 jfr CLI)
jfr summary tlab.jfr
```

핵심 이벤트:
- `jdk.ObjectAllocationInNewTLAB` — TLAB 가득 차서 새 TLAB 받은 케이스
- `jdk.ObjectAllocationOutsideTLAB` — TLAB 못 받고 Eden 직접 할당 (slow path) — **많으면 문제**
- `jdk.GarbageCollection` — GC 종합
- `jdk.G1HeapRegionTypeChange` — region 상태 변경 (Humongous 추적)

### `OutsideTLAB`이 많이 나오면

원인:
1. **큰 객체 빈번 할당** — `byte[]`, `String.toCharArray()` 등.
2. **TLAB 크기 부족** — 동적 조정이 따라가지 못함.

조치:
- `-XX:+PrintTLAB` 또는 JFR로 정확한 객체 타입 파악.
- 큰 배열을 startup에 미리 할당하고 재사용 (object pool).
- `-XX:MinTLABSize`, `-XX:TLABSize` 미세 조정.

### Humongous 추적

```bash
# GC log
java -Xlog:gc+humongous=debug -jar app.jar

# 출력 예
# [gc,humongous] Humongous allocation: 5242880 bytes, allocation request: ...
```

또는 JFR `jdk.G1HeapRegionTypeChange` 이벤트로 Humongous region 생성 추적.

### Allocation Profiling (async-profiler)

```bash
# 다운로드: https://github.com/async-profiler/async-profiler
asprof -e alloc -d 30 -f alloc.html <pid>

# alloc.html을 브라우저로 열어 flame graph 보기
# → 어느 메서드/스택이 할당 hot path인지 발견
```

### 운영 함정 진단 시나리오

| 증상 | 진단 명령 | 가능한 원인 |
|---|---|---|
| `OutOfMemoryError: Java heap space` | heap dump + MAT | 메모리 누수, Heap 부족 |
| Full GC 매분 발생 | `jstat -gc 1s` 또는 GC log | Old gen 압박, premature promotion |
| Young GC가 너무 길다 | `-Xlog:gc+phases=debug` | Heap 너무 큼, Survivor 부족 |
| P99 latency 튐 | JFR `jdk.GarbageCollection` | STW 길이 vs 목표 |
| RSS는 큰데 Heap은 안 크다 | NMT (`jcmd VM.native_memory`) | Metaspace/Direct Memory/Code Cache |

---

## ⚔️ 8단계: 꼬리질문 트리

### Q1. Heap의 구조를 설명하세요.

**예상 답변**:
> Young Generation + Old Generation으로 나뉜다.
> Young은 Eden + Survivor 0 + Survivor 1 (기본 8:1:1).
> 새 객체는 Eden에 할당. Minor GC에서 살아남으면 Survivor로, 충분히 살면 Old로 promote.
> G1에서는 추가로 Humongous region이 있어 region 크기의 50% 이상 객체를 별도 처리.
> JDK 8까지 있던 PermGen은 Metaspace(native 메모리)로 이동.

#### 🪝 꼬리 Q1-1: "그럼 Eden과 Survivor 비율은 어떻게 결정되나요?"

**예상 답변**:
> 기본 `-XX:SurvivorRatio=8` → Eden : S0 : S1 = 8:1:1.
> Eden이 Young의 80%, S0/S1이 각 10%.
> Young 자체는 `-XX:NewRatio=2` (Old:Young = 2:1)로 전체 Heap의 1/3.
> 부하/워크로드에 따라 JVM이 동적으로 조정.

##### 🪝 꼬리 Q1-1-1: "Survivor 비율을 조정하는 게 의미 있나요?"

**예상 답변**:
> 워크로드에 따라 다름.
> 단명 객체 많으면 Survivor 작아도 됨 (Eden 크게).
> 중기 객체 많으면 Survivor 키워야 함 (premature promotion 회피).
> 진단: JFR `jdk.GCSurvivorAge` 또는 `-XX:+PrintTenuringDistribution`.
> 단, JVM의 동적 조정이 대부분 잘 되므로 명시 튜닝은 측정 후에만.

### Q2. TLAB이 무엇이고 왜 필요한가요?

**예상 답변**:
> Thread-Local Allocation Buffer.
> Eden 안에서 각 스레드가 미리 확보한 작은 영역.
> 객체 할당 시 lock 없이 bump-the-pointer로 즉시 할당.
> 없으면 모든 스레드가 Eden.top을 동시 갱신하려고 lock 경합 → 멀티코어에서 할당 직렬화.
> 기본 크기는 JVM이 자동 조정 (64KB~수 MB).

#### 🪝 꼬리 Q2-1: "TLAB이 가득 차면 어떻게 되나요?"

**예상 답변**:
> 두 경로:
> 1. **Retire & Refill**: 남은 자투리를 filler object(dummy `int[]`)로 채워서 GC가 인식할 수 있게 한 후 새 TLAB 받음.
> 2. **Slow Path**: 객체 하나만 Eden에 직접 할당 (lock 또는 CAS).
> 어느 쪽이냐는 남은 공간 비율과 객체 크기 휴리스틱.

##### 🪝 꼬리 Q2-1-1: "filler object가 왜 필요하나요?"

**예상 답변**:
> GC가 Heap을 walking할 때 일관된 객체 경계를 가정.
> TLAB의 남은 공간을 그냥 두면 그 영역의 메모리 내용이 무엇인지 모름.
> `int[size]` 같은 dummy 객체로 채우면 GC가 "여긴 dead int 배열" 로 인식하고 건너뜀.
> HotSpot의 `CollectedHeap::fill_with_object`가 이 역할.

#### 🪝 꼬리 Q2-2: "TLAB을 너무 크게 잡으면?"

**예상 답변**:
> 1. Eden 단편화: 많은 스레드가 큰 TLAB을 가지면 일부만 사용 후 retire하는 비효율.
> 2. Eden 빨리 가득 → Minor GC 자주.
> 3. 컨테이너에서 스레드 수 많으면 Eden 부족 위험.
> 그래서 `-XX:ResizeTLAB` (기본 on) — JVM이 할당 패턴 관찰해 동적 조정.

### Q3. Humongous Object가 뭐고 왜 운영 함정인가요?

**예상 답변**:
> G1 GC에서 region 크기의 50% 이상인 큰 객체.
> 일반 객체와 달리 **Old gen에 직접 할당** → Young GC 안 거침.
> 문제:
> 1. 일찍 죽어도 회수 늦음 (Old GC 기다림).
> 2. 연속 region 점유 — fragmentation.
> 3. 4MB region에 5MB 객체면 region 2개 점유 (1개는 일부만 사용 — 낭비).
> 진단: `-Xlog:gc+humongous=debug` 또는 JFR `jdk.G1HeapRegionTypeChange`.
> 회피: startup에 미리 할당 + 재사용 (object pool), `-XX:G1HeapRegionSize` 조정.

#### 🪝 꼬리 Q3-1: "ZGC에서도 Humongous 개념이 있나요?"

**예상 답변**:
> ZGC는 region이 아닌 **page** 단위 (Small/Medium/Large).
> Small: 2MB (객체 ≤ 256KB)
> Medium: 32MB (객체 ≤ 4MB)
> Large: 동적 (객체 > 4MB) — 한 페이지에 한 객체.
>
> G1의 Humongous와 비슷한 처리 (큰 객체는 단일 페이지). 단점은 비슷 — 큰 객체의 fragmentation 위험.

### Q4. Object Header에는 무엇이 들어있나요?

**예상 답변**:
> Mark Word (8B) + Klass Pointer (4B compressed / 8B).
> Mark Word는 객체 상태에 따라 의미가 다름:
> - Unlocked: hash code + age + lock bits
> - Biased: 소유 thread id + epoch
> - Lightweight Lock: lock record 포인터
> - Heavyweight Lock: monitor 포인터
> - GC mark: forwarding pointer 또는 mark bit
> Klass Pointer는 객체의 클래스 메타데이터(InstanceKlass)를 가리킴.

#### 🪝 꼬리 Q4-1: "Compressed Oops가 뭐고 왜 Heap 32GB까지만 활성화되나요?"

**예상 답변**:
> 64-bit JVM에서 객체 참조를 32-bit로 압축.
> 압축: oop = (실제 주소 - heap_base) >> 3 (3은 8바이트 정렬).
> 4GB × 8 = 32GB 까지 표현 가능.
> Heap이 그 이상이면 압축 불가 → 자동으로 64-bit oop 사용.
> 메모리 ~30% 절감 + 캐시 효율 ↑.
> "32GB의 벽" — 31GB에서 안 죽으면 31GB가 32GB 이상보다 더 효율.

##### 🪝 꼬리 Q4-1-1: "Klass Pointer도 압축되나요?"

**예상 답변**:
> Yes. **Compressed Class Pointer**.
> Metaspace 안에 별도 **Compressed Class Space** (기본 1GB).
> `-XX:CompressedClassSpaceSize`로 조정.
> Heap의 oop 압축과 독립적이지만, `-XX:+UseCompressedOops`가 켜져 있으면 자동 활성.
> Class 수 많은 앱(Spring Boot)에서 1GB 한계가 OOM:Metaspace 원인이 되기도 함.

### Q5. PermGen이 왜 죽고 Metaspace가 도입됐나요?

**예상 답변**:
> PermGen의 문제:
> 1. 크기 고정 → 동적 클래스 생성(Spring AOP, Hibernate proxy, Mockito) 많은 앱에서 OOM 빈발.
> 2. Heap 안의 generation이라 GC 정책에 끼어듦, ClassLoader unload 비효율.
> 3. Compressed Oops와 충돌 (Klass 포인터 압축).
>
> Metaspace:
> - Heap 밖 native 메모리.
> - 기본 무제한 (`-XX:MaxMetaspaceSize`로 제한 가능).
> - ClassLoaderData 단위로 chunk 할당 → CL unload 시 통째 free.
> - String Pool은 Heap의 일반 영역으로 이동.

### Q6. (Killer) `-Xmx2g`로 시작한 JVM이 `top`에서 RSS 4GB로 보입니다. 어떻게 진단하시겠어요?

**예상 답변**:
> 1. **Native Memory Tracking 활성화**:
>    ```
>    java -XX:NativeMemoryTracking=summary -jar app.jar
>    jcmd <pid> VM.native_memory summary
>    ```
> 2. 출력에서 각 영역 commit 합계 확인:
>    - Java Heap (committed)
>    - Class (Metaspace + Compressed Class Space)
>    - Thread (스레드 스택 × N)
>    - Code (Code Cache)
>    - GC (자료구조)
>    - Internal (JVM 내부)
> 3. 일반적 분포: Heap 2GB + Metaspace 200MB + Code Cache 240MB reserve + Threads 500MB (500 thread × 1MB) + Direct Memory + GC 자료구조 = 약 3.5~4GB.
> 4. 비정상이면:
>    - Metaspace 비대 → ClassLoader 누수 (jcmd VM.classloader_stats)
>    - Direct Memory 비대 → DirectBuffer 누수
>    - Thread 비대 → 스레드 수 폭증 (jstack)
> 5. 컨테이너 환경이면 limit의 50~70%로 `-Xmx` 설정 권장.

#### 🪝 꼬리 Q6-1: "NMT의 reserved vs committed 차이는?"

**예상 답변**:
> - **reserved**: JVM이 OS에게 "이 가상 주소 공간을 우리 거다"라고 표시. 아직 실제 메모리 사용 아님.
> - **committed**: 실제로 물리 메모리에 매핑. RSS에 잡힘.
> 예: Heap `-Xmx4g`면 reserve 4GB, committed는 -Xms ~ 현재 사용량.
> Code Cache 기본 240MB reserve, committed는 현재 컴파일된 코드 양만큼.
>
> `top`의 VSZ ≈ reserved, RSS ≈ committed.

---

## 🔗 다음 단계

- → [02. Metaspace & Class Space](./02-metaspace-and-class-space.md): PermGen 죽음의 풀버전, ClassLoaderData
- → [03. Stack & PC & Native Stack](./03-stack-pc-native.md): Per-Thread 영역
- → [04. Code Cache](./04-code-cache.md): JIT 결과 저장소
- → [05. Direct Memory](./05-direct-memory.md): Off-heap NIO

## 📚 참고

- **JVMS §2.5 (Run-Time Data Areas)**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.5
- **HotSpot Glossary - Heap**: https://openjdk.org/groups/hotspot/docs/HotSpotGlossary.html
- **JEP 122 (Remove PermGen)**: https://openjdk.org/jeps/122
- **G1 GC Tuning Guide**: https://docs.oracle.com/en/java/javase/21/gctuning/garbage-first-g1-garbage-collector1.html
- **HotSpot `threadLocalAllocBuffer.hpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/shared/threadLocalAllocBuffer.hpp
- **HotSpot `g1CollectedHeap.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/g1/g1CollectedHeap.cpp
- **async-profiler**: https://github.com/async-profiler/async-profiler
- **Eclipse MAT**: https://www.eclipse.org/mat/
