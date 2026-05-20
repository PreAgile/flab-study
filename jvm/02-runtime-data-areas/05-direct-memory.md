# 02-05. Direct Memory — Heap 밖, GC 너머의 메모리

> `ByteBuffer.allocate(1024)`는 Heap에 1KB.
> `ByteBuffer.allocateDirect(1024)`는 어디에 1KB를 할당하는가? **Heap이 아니다. OS의 native 메모리.**
> 이 메모리는 GC가 직접 관리하지 않는다. DirectByteBuffer 객체(Heap에 있음)가 unreachable이 되어 GC될 때, 그 객체의 **Cleaner**(PhantomReference)가 `free()`를 호출한다.
> "DirectByteBuffer 객체는 GC됐는데 native memory는 아직 살아 있는" 순간이 길어지면 — Direct Memory 누수, 컨테이너 OOM-killed의 흔한 원인.

---

## 이 문서의 사용법

이 문서는 **면접용 마인드맵**을 따라 선형으로 펼친 구조다. 학습 순서 = 면접 답변 순서 = 백지에 그리는 순서.

1. **0장 마인드맵을 먼저 외운다** — 루트 한 문장 + 6가지 가지 + 각 가지의 키워드 3개.
2. **1~6장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 정확히 대응.
3. **7장 면접 워크플로우로 검증**.
4. **8장 꼬리질문으로 깊이 점검**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"Direct Memory는 Heap 밖 native 메모리(malloc/mmap)이고, Heap의 DirectByteBuffer 객체가 GC될 때 Cleaner(PhantomReference)가 native free를 호출하는 두 단계 해제 모델이다."**

이 한 문장에서 모든 답변이 출발한다.

### 6개 가지 — 순서를 외운다

```
                  [ROOT: Direct Memory = off-heap + Cleaner 해제]
                                    │
       ┌─────────┬──────────────┬───┴───┬──────────────┬─────────┐
       │         │              │       │              │         │
      ① WHY    ② WHAT         ③ HOW   ④ Mapped       ⑤ 운영    ⑥ 진화
   Zero-copy  Heap객체+native Cleaner Buffer        누수 5패턴 Foreign
       │         │              │       │              │         │
       │    ┌────┼────┐     ┌───┼───┐  ┌─┼─┐      ┌────┼────┐    │
    1번vs2번 DirectBB  PhantomRef       mmap vs   Cleaner지연  NIO 1.4
    복사    address    ReferenceHandler malloc    Mapped누수  Cleaner JDK8/9
    pinning Bits회계   System.gc()      OS page    Netty누수  Foreign JDK22
    풀링비용 -XX:MaxDirectMem  안전판   cache       JNI 누수
                                       MaxDirect    DisableGC
                                       카운트X
```

### 가지별 핵심 키워드 (각 가지 3개씩만)

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① WHY Zero-copy** | 일반 read: 디스크→커널→Heap (2회 복사) | Direct: 디스크→Direct (1회 복사) | Heap pinning 문제 |
| **② WHAT 위치** | Heap에 DirectByteBuffer 객체(작음) | Native에 데이터(큼), `address`로 연결 | -XX:MaxDirectMemorySize |
| **③ HOW Cleaner** | PhantomReference 기반 | ReferenceHandler thread | System.gc() 안전판 |
| **④ Mapped vs Direct** | mmap vs malloc | OS page cache (Mapped) | MaxDirect 카운트 안 됨 (Mapped) |
| **⑤ 운영** | OOM:Direct buffer memory | 컨테이너 OOM-killed 진단 | Netty PARANOID, jcmd NMT |
| **⑥ 진화** | JDK 1.4 NIO | JDK 9 java.lang.ref.Cleaner | JDK 22 Foreign Memory (JEP 454) |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 질문에 맞는 가지 1개 선택 → 그 가지의 키워드 3개 순서대로 설명 → 듣는 사람의 관심에 따라 인접 가지로 확장

---

## 1. 가지 ①: WHY — Direct Memory가 왜 따로 있나

### 1.1 핵심 질문

> "Heap Buffer가 있는데 왜 Direct Buffer를 따로 두나요?"

### 1.2 키워드 1 — Zero-copy I/O (메모리 복사 절감)

**일반 Heap Buffer로 파일 read 시 (2번 복사)**:
```
[디스크]
   │ (1) DMA로 커널 page cache로
   ▼
[커널 page cache] ───────────────►  (2) 커널 → JVM Heap 복사 (CPU)
                                                ↓
                                  [Heap의 byte[] / HeapByteBuffer]
```

**Direct Buffer로 read 시 (1번 복사)**:
```
[디스크]
   │ (1) DMA로 Direct Buffer로 직접
   ▼
[Direct Buffer (native 메모리)] ◄── 사용자 코드 직접 접근
```

→ **고처리량 I/O 시스템(Netty, Kafka, gRPC, Cassandra)이 Direct Buffer를 쓰는 이유**. 메모리 복사 50% 절감 + cache pollution 감소.

### 1.3 키워드 2 — Heap Buffer의 pinning 문제

**왜 Heap에서는 안 되는가**:
- GC가 객체를 옮길 수 있음 (Compacting GC) → 커널이 그 주소를 직접 쓸 수 없음.
- JVM이 syscall 직전 임시 Direct Buffer로 복사 후 syscall.
- 그래서 Heap Buffer로 NIO 호출하면 **내부적으로 Direct로 한 번 더 복사**.

Direct Buffer는 native 주소가 변하지 않음 → 커널이 직접 read/write.

### 1.4 키워드 3 — 풀링 비용 (Direct가 항상 빠른 건 아님)

```
Heap Buffer 할당: TLAB bump-the-pointer (~3 instruction)
Direct Buffer 할당: native malloc + Cleaner 등록 + page commit (~수 us)

→ 1000배 차이
```

**그래서 수명 긴 버퍼만 Direct**. Short-lived는 Heap이 더 빠름. 그래서 Netty의 PooledByteBufAllocator 같은 풀링이 필요.

**경험칙**:
- < 1KB + 단명: Heap.
- > 1MB + I/O: Direct.
- 중간: 풀링 사용.

### 1.5 택배 비유

> - **Heap Buffer** = 회사 창고(Heap) 안의 임시 상자. GC가 정기 청소.
> - **Direct Buffer** = 회사 밖의 별도 임대 창고. GC 청소 안 함. 별도 계약(Cleaner)으로 해제.
> - **MappedByteBuffer** = 외부 데이터 센터의 원본 파일을 사무실에서 직접 들여다보는 윈도우.
> - **Cleaner** = 임대 창고 사용자가 죽으면 자동으로 계약 해지를 통보하는 변호사.
> - **누수** = 사용자(DirectByteBuffer)는 죽었는데 변호사가 늦게 통지 → 임대료(메모리) 계속.

---

## 2. 가지 ②: WHAT — Direct Memory의 위치와 구조

### 2.1 핵심 질문

> "DirectByteBuffer를 그려보세요. Heap과 어떻게 연결되어 있나요?"

### 2.2 키워드 1 — Heap의 작은 객체 + Native의 큰 데이터

```
[Java Heap]                              [Native Memory]
┌────────────────────────────┐           ┌──────────────────────┐
│ DirectByteBuffer 객체        │           │ Native allocated     │
│  ├── address (long)         │           │ buffer (예: 1MB)     │
│  │       │                  │           │                       │
│  │       └──────────────────┼──────────►│ ◄── 실제 데이터        │
│  ├── capacity, position, ...│           │                       │
│  └── Cleaner (PhantomRef)   │           └──────────────────────┘
└────────────────────────────┘                      ▲
         │                                          │
         │ GC됨                                      │ free() 호출
         ▼                                          │
    [Cleaner.clean()] ────────────────────────────────┘
```

**`DirectByteBuffer` 내부 (간략화)**:
```java
class DirectByteBuffer extends MappedByteBuffer {
    long address;          // ★ Native 메모리 시작 주소
    int  capacity;
    int  position, limit, mark;
    Cleaner cleaner;       // GC 시 native free 호출자

    DirectByteBuffer(int cap) {
        long addr = UNSAFE.allocateMemory(cap);
        UNSAFE.setMemory(addr, cap, (byte) 0);
        this.address = addr;
        this.capacity = cap;
        this.cleaner = Cleaner.create(this, new Deallocator(addr, cap));
    }

    public byte get(int index) {
        return UNSAFE.getByte(address + index);   // 직접 native 접근
    }
}
```

→ **Heap에 작은 메타데이터 객체, Native에 큰 데이터**. 둘이 `address` 필드로 연결.

### 2.3 키워드 2 — Bits 회계 (Direct Memory 한계 추적)

```java
class Bits {
    private static final AtomicLong RESERVED_MEMORY = new AtomicLong();

    static void reserveMemory(long size, int cap) {
        long max = maxMemory();  // -XX:MaxDirectMemorySize
        if (RESERVED_MEMORY.get() + size > max) {
            // ★ System.gc() 트리거 → Cleaner들 처리
            System.gc();
            // 다시 체크 - 여전히 부족하면 OOM
            if (RESERVED_MEMORY.get() + size > max) {
                throw new OutOfMemoryError("Direct buffer memory");
            }
        }
        RESERVED_MEMORY.addAndGet(size);
    }
}
```

**핵심 관찰**:
- DirectByteBuffer 생성 시 `reserveMemory` 호출 → Direct Memory 한계 체크.
- 한계 초과 시 **System.gc() 강제 호출** → Cleaner 트리거.
- `-XX:+DisableExplicitGC` 켜면 이 호출 무력화 → **NIO 사용 앱에서 절대 켜지 말 것**.
- 9번까지 sleep + retry 후 최종 OOM.

### 2.4 키워드 3 — -XX:MaxDirectMemorySize와 전체 메모리 그림

```
JVM Process Memory
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Shared]                  [JVM-managed Native]    [★ Direct ★]

┌────────────┐            ┌────────────┐           ┌─────────────────────┐
│ Java Heap   │            │ Metaspace   │           │ DirectByteBuffer     │
│  -Xmx 2g    │            │             │           │  - malloc된 영역     │
│  GC 대상    │            │             │           │  - Cleaner로 free    │
└────────────┘            └────────────┘           │  -XX:MaxDirectMem    │
                                                    ├─────────────────────┤
┌────────────┐            ┌────────────┐           │ MappedByteBuffer     │
│ Stacks     │            │ Code Cache  │           │  - mmap된 파일       │
└────────────┘            └────────────┘           │  - OS page cache 사용 │
                                                    │  - -XX:MaxDirectMem  │
                                                    │     에 카운트 안 됨!  │
                                                    └─────────────────────┘
```

**MaxDirectMemorySize 기본값**: 명시 안 하면 **-Xmx와 비슷** (Runtime.maxMemory() 기반). 즉 `-Xmx 2g`면 Direct도 최대 2g까지 — Heap과 합치면 컨테이너 limit 초과 가능. **Container 환경에서는 명시 권장**: `-Xmx2g -XX:MaxDirectMemorySize=512m`.

---

## 3. 가지 ③: HOW — Cleaner 메커니즘

### 3.1 핵심 질문

> "DirectByteBuffer의 native 메모리는 누가, 언제 해제하나요?"

### 3.2 키워드 1 — PhantomReference 기반 두 단계 해제

```
일반 객체 lifecycle:
   생성 → 사용 → unreachable → GC가 회수 → 메모리 free

DirectByteBuffer lifecycle:
   생성 → native malloc → Cleaner 등록 → 사용
        → unreachable → GC가 객체 회수
        → 그러나 native 메모리는 아직 살아있음 ★
        → ReferenceHandler가 PhantomReference 발견
        → Cleaner.clean() 호출 → native free()
        → 비로소 native 메모리 해제
```

**왜 두 단계인가**:
- finalize는 deprecated (예측 불가, 성능, 보안).
- PhantomReference는 객체 GC 후에도 Cleaner가 살아있어 native free 보장.
- **단점: GC와 native free 사이 지연**. 짧은 시간 폭주 시 OOM.

### 3.3 키워드 2 — 세 스레드 협력

```
[Application Thread]
DirectByteBuffer buf = ByteBuffer.allocateDirect(1MB);
  → Bits.reserveMemory(1MB)
  → UNSAFE.allocateMemory(1MB) → native pointer P
  → new DirectByteBuffer(P, 1MB)
  → Cleaner.create(buf, new Deallocator(P, 1MB))
       → Deallocator를 PhantomReference로 ReferenceQueue에 등록

[Application Thread]
buf = null;   // unreachable

[GC Thread]
- buf 객체가 unreachable → Cleaner(PhantomRef)가 enqueue 대상

[Reference Handler Thread]
- ReferenceQueue 모니터링
- Cleaner 발견 → Cleaner.clean() 호출
       → Deallocator.run()
            → UNSAFE.freeMemory(P)  ← Native 메모리 해제
            → Bits.unreserveMemory(1MB)
```

→ **Application(생성), GC(객체 회수), Reference Handler(Cleaner 실행)** 협력.

### 3.4 키워드 3 — System.gc() 안전판

Bits.reserveMemory가 한계 도달 시:
1. 새 할당 + 현재 사용량 ≤ MaxDirectMemorySize?
2. 아니면 **System.gc() 강제 호출** → 일반 GC 트리거 → PhantomReference 처리 → 일부 free.
3. 그래도 부족하면 `OutOfMemoryError: Direct buffer memory`.

**OOM 메시지 정확한 형태**:
```
java.lang.OutOfMemoryError: Cannot reserve 1048576 bytes of direct buffer memory
  (allocated: 1073741824, limit: 1073741824)
    at java.base/java.nio.Bits.reserveMemory(Bits.java:175)
    at java.base/java.nio.DirectByteBuffer.<init>(DirectByteBuffer.java:118)
    at java.base/java.nio.ByteBuffer.allocateDirect(ByteBuffer.java:317)
```
→ `allocated`가 `limit`에 도달.

**Cleaner와 finalize의 차이**:
| | finalize | Cleaner |
|---|---|---|
| 메커니즘 | 객체에 finalize 메서드 | PhantomReference 별도 thread |
| 시점 | GC가 객체 회수 전 | 객체 GC 후 |
| 인스턴스 누수 위험 | 있음 (this를 다시 살릴 수 있음) | 없음 (객체-cleanup 분리) |
| 표준화 | deprecated (JDK 9+) | `java.lang.ref.Cleaner` public |

---

## 4. 가지 ④: MappedByteBuffer — Direct와의 차이

### 4.1 핵심 질문

> "MappedByteBuffer와 DirectByteBuffer는 어떻게 다른가요?"

### 4.2 키워드 1 — mmap vs malloc

```java
RandomAccessFile raf = new RandomAccessFile("data.bin", "rw");
FileChannel ch = raf.getChannel();
MappedByteBuffer mb = ch.map(FileChannel.MapMode.READ_WRITE, 0, 1024 * 1024);
// → mmap syscall로 1MB를 파일에 매핑
// → 메모리 read/write가 즉시 파일에 반영
```

| | DirectByteBuffer | MappedByteBuffer |
|---|---|---|
| 메모리 출처 | malloc (anonymous) | mmap (파일) |
| 디스크와 관계 | 무관 | 페이지 단위 매핑 |
| 영속성 | 프로세스 종료 시 사라짐 | 파일에 남음 |
| 디스크 sync | 수동 (FileChannel.write) | 자동 (페이지 단위 lazy) |

### 4.3 키워드 2 — OS Page Cache 활용

```
[일반 file read/write]
read(fd, buf, size)
  └→ 커널이 디스크 → page cache 로 가져옴
  └→ page cache → 사용자 buf로 copy

[MappedByteBuffer]
mb.get(i)
  └→ 페이지 fault if 첫 접근
  └→ 커널이 디스크 → page cache 로 가져옴
  └→ 사용자가 page cache 메모리에 직접 read (copy 없음)

[DirectByteBuffer + Channel.read]
ch.read(directBuf)
  └→ DMA가 디스크 → directBuf의 native 메모리로
```

→ MappedByteBuffer가 page cache 사용 = **OS가 메모리 압박 시 자동 evict 가능**. Direct Buffer는 JVM 책임.

### 4.4 키워드 3 — MaxDirectMemorySize에 카운트 안 됨 (함정)

| | MappedByteBuffer | DirectByteBuffer |
|---|---|---|
| -XX:MaxDirectMemorySize 카운트 | **❌ 안 됨** | ✅ 카운트 |
| BufferPoolMXBean | `mapped` pool | `direct` pool |
| 해제 | unmap (mmap unmap) | free (malloc) |
| 적합 워크로드 | 큰 파일 random access (DB, log) | 네트워크 I/O |

**MappedByteBuffer 해제의 함정**:
```java
RandomAccessFile raf = new RandomAccessFile("big.bin", "rw");
MappedByteBuffer mb = raf.getChannel().map(MapMode.READ_WRITE, 0, 10_000_000_000L); // 10GB
// 사용 후 raf.close() 해도 mmap은 즉시 해제 안 됨
// → mb가 GC돼야 unmap, 그 전까지는 OS 가상 메모리 점유
```

**해결**:
- JDK 9+: 명시적 unmap API 없음 (보안).
- 옵션: `Unsafe.invokeCleaner(mb)` (JDK 17+ Strong Encapsulation 제약).
- **JDK 22+ Foreign Memory API의 Arena** — try-with-resources로 deterministic unmap.
- 정공법: 작은 단위로 분할 mmap 후 사용 후 명시적 null.

---

## 5. 가지 ⑤: 운영 — 누수 진단

### 5.1 핵심 질문

> "Direct Memory 관련 누수를 어떻게 진단하고 해결하나요?"

### 5.2 키워드 1 — 누수 5대 패턴

| # | 패턴 | 원인 | 진단 |
|---|---|---|---|
| 1 | **Cleaner 트리거 지연** | Young GC만 자주, Cleaner thread가 못 따라감 | Heap 객체는 사라졌는데 native는 살아있음 |
| 2 | **MappedByteBuffer 해제 불가** | mmap unmap 누락, raf.close()해도 mb GC 기다림 | `pmap`에 큰 file mapping 누적 |
| 3 | **Netty 누수** | `ReferenceCountUtil.release()` 누락, 풀이 새 chunk 계속 할당 | `-Dio.netty.leakDetection.level=PARANOID` |
| 4 | **JNI 라이브러리 직접 malloc** | JNI 코드가 malloc 후 free 없음. NMT가 못 봄 | `jemalloc`, Valgrind |
| 5 | **-XX:+DisableExplicitGC + 폭주** | System.gc() 무력화 → Cleaner 트리거 못 함 → OOM | 옵션 점검 |

### 5.3 키워드 2 — 진단 도구 (jcmd / pmap / BufferPool / Netty PARANOID)

**① jcmd NMT** — Direct Memory가 `Other` 또는 `Internal` 카테고리:
```bash
java -XX:NativeMemoryTracking=detail -jar app.jar
jcmd <pid> VM.native_memory detail
```
**한계**: JNI native 라이브러리의 직접 malloc은 NMT가 못 봄.

**② BufferPoolMXBean** — DirectByteBuffer 정확한 합계:
```java
List<BufferPoolMXBean> pools = ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class);
for (BufferPoolMXBean pool : pools) {
    System.out.println(pool.getName() + ": " + pool.getCount() + " buffers, "
                       + pool.getMemoryUsed() + " bytes");
}
// direct: 1234 buffers, 567890123 bytes
// mapped: 5 buffers, 1073741824 bytes
```

**③ pmap** — OS 레벨 메모리 맵:
```bash
pmap -x <pid> | sort -k 2 -n -r | head
# Address           Kbytes     RSS   Dirty Mode  Mapping
# 00007f7e8c000000   65536   65532   65532 rw-p- [anon]   ← Heap/Direct 후보
# 00007f7eb0000000 1048576   23456   23456 r--s- big.bin  ← MappedByteBuffer
```
`[anon]` 큰 영역이 RSS와 일치하면 DirectByteBuffer 후보. 파일 매핑은 파일명 표시.

**④ Netty PARANOID** — Netty 누수 추적:
```bash
java -Dio.netty.leakDetection.level=PARANOID -jar app.jar
```
레벨: DISABLED / SIMPLE(기본 1%) / ADVANCED / PARANOID(100%, 운영 환경에서 느림).

**⑤ JFR**: `jdk.DirectBufferStatistics`, `jdk.NativeMemoryUsage` 이벤트.

### 5.4 키워드 3 — Killer 시나리오 + 운영 매트릭스

**시나리오 1: Container OOM-killed인데 Heap dump 정상 (5GB limit, -Xmx 2GB)**

진단 단계:
1. `jcmd VM.native_memory summary` — Heap 2GB + Metaspace + Threads + Code Cache + **Other** 합산. Other 비정상 크면 Direct 의심.
2. BufferPoolMXBean — `direct` pool 사용량. **MaxDirectMemorySize 설정 안 했고 -Xmx만큼 자동 부여**됐을 수 있음.
3. `pmap -x <pid>` — 큰 anonymous 영역 또는 파일 매핑.
4. Netty 사용 중이면 PARANOID 모드 → release 누락 stack trace.
5. JNI 의심 — NMT 합과 RSS 차이 크면 `jemalloc`.
6. 조치: 누수 코드 수정 + 명시적 한계 (`-XX:MaxDirectMemorySize=512m`).

**컨테이너 메모리 분배 가이드라인 (5GB limit 기준)**:
- `-Xmx`: 2g (40%)
- `-XX:MaxDirectMemorySize`: 1g (20%)
- `-XX:MaxMetaspaceSize`: 512m (10%)
- `-XX:ReservedCodeCacheSize`: 256m
- Thread stacks (500 × 1MB): 500m
- 여유: ~700m (JVM 내부, page cache, JNI)

**운영 매트릭스**:
| 증상 | 진단 명령 | 가능 원인 |
|---|---|---|
| `OOM: Direct buffer memory` | BufferPool.getMemoryUsed() | DirectByteBuffer 한계 도달 |
| Container OOM-killed + Heap dump 정상 | `pmap` + NMT | Direct/Mapped 누수 |
| RSS는 큰데 NMT 합 안 맞음 | `jemalloc` | JNI 라이브러리 누수 |
| Netty 앱 시간 지나 메모리 ↑ | PARANOID 레벨 | release 누락 |
| MappedByteBuffer 해제 안 됨 | `pmap` 누적 | mmap unmap 누락 |
| System.gc() 후에도 누적 | `-XX:+DisableExplicitGC` 점검 | 옵션 함정 |

---

## 6. 가지 ⑥: 진화 — NIO부터 Foreign Memory까지

### 6.1 핵심 질문

> "Direct Memory API는 어떻게 진화해왔고, 미래는?"

### 6.2 키워드 1 — JDK 1.4 NIO 도입

| 연도 | JDK | 변화 | 이유 |
|---|---|---|---|
| 2002 | 1.4 | NIO 도입 (`java.nio`) + Direct Buffer | 고처리량 I/O |
| 2004 | 5 | `MaxDirectMemorySize` 옵션 | 무제한 할당 사고 방지 |

NIO의 동기: 자바 1.0~1.3은 stream-based I/O만 → 멀티 connection 처리 시 thread 폭증. NIO는 Selector + Channel + ByteBuffer 모델로 한 thread가 수천 connection.

### 6.3 키워드 2 — Cleaner 표준화 (JDK 8 → 9)

| 연도 | JDK | 변화 | 이유 |
|---|---|---|---|
| 2014 | 8 | `sun.misc.Cleaner` 정착 | finalize 회피 |
| 2017 | 9 | `jdk.internal.ref.Cleaner` (모듈화) | sun.misc 폐기 단계 |
| 2017 | 9 | **`java.lang.ref.Cleaner` public API** | 사용자도 Cleaner 사용 가능 |
| 2021 | 17 | `sun.misc.Unsafe.invokeCleaner` 폐기 시작 | 보안, Strong Encapsulation |

**JDK 9의 의의**: Cleaner가 public API로 노출 → 사용자 코드도 PhantomReference 기반 정리 가능. `java.lang.ref.Cleaner` + `Cleaner.Cleanable` 패턴.

### 6.4 키워드 3 — Foreign Memory API (JDK 22, JEP 454) — 미래

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment seg = arena.allocate(1024);  // Direct Memory 할당
    seg.set(ValueLayout.JAVA_INT, 0, 42);
    int x = seg.get(ValueLayout.JAVA_INT, 0);
}  // Arena가 자동 unmap — try-with-resources로 명시적 해제
```

**의의**: **deterministic free**. Cleaner의 비결정적 free 문제 해결. DirectByteBuffer를 점진적으로 대체.

| | Cleaner 모델 | Foreign Memory Arena |
|---|---|---|
| 해제 시점 | 비결정적 (GC 후 ReferenceHandler) | 결정적 (close 호출 시) |
| 누수 위험 | 누수 가능 (release 누락) | try-with-resources로 보장 |
| API | DirectByteBuffer | MemorySegment, Arena |
| 등장 | JDK 9 | JDK 22 (JEP 454) |

→ 점진적으로 Direct Memory 사용 패턴이 Foreign Memory API로 이동 중. 새 코드는 Arena 권장.

---

## 7. 면접 답변 워크플로우

### 7.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "allocate vs allocateDirect 차이?" | ① WHY (Zero-copy) | ② WHAT (위치) |
| "Cleaner 동작?" | ③ HOW | ② WHAT (Bits) |
| "OOM: Direct buffer memory 메커니즘?" | ② WHAT (Bits) | ③ HOW (System.gc 안전판) |
| "MappedByteBuffer와 Direct 차이?" | ④ Mapped | ⑤ 운영 (해제 함정) |
| "Netty가 풀링하는 이유?" | ① WHY (할당 비용) | ⑤ 운영 (누수) |
| "Container OOM, Heap 정상" | ⑤ 운영 (Killer) | ② WHAT (분배) |
| "Foreign Memory가 뭐?" | ⑥ 진화 | ③ HOW (Cleaner와 비교) |

### 7.2 답변 템플릿

> **루트 문장 한 줄 → 해당 가지 키워드 3개 → 듣는 사람 표정 보고 인접 가지로**

예: "Cleaner는 무엇이고 어떻게 동작하나요?"

> "Direct Memory는 Heap 밖 native이고 GC가 직접 관리 안 합니다. (← 루트)
> 첫째, **PhantomReference 기반** — DirectByteBuffer 생성 시 Cleaner.create(buf, deallocator)로 등록.
> 둘째, **세 스레드 협력** — Application(생성), GC(객체 회수 시 Cleaner enqueue), **ReferenceHandler thread**가 queue 모니터링 → Cleaner.clean() → UNSAFE.freeMemory.
> 셋째, **System.gc() 안전판** — Bits.reserveMemory가 한계 도달 시 강제 GC로 pending Cleaner 처리. 그래서 `-XX:+DisableExplicitGC`를 NIO 앱에서 켜면 OOM 더 쉽게 발생.
> 한계는 GC와 native free 사이 지연 — 짧은 시간 폭주 시 OOM. JDK 22+ Foreign Memory API의 Arena가 deterministic 해제로 이걸 풀려는 방향입니다."

---

## 8. 꼬리질문 트리 (가지별)

### Q1 [가지 ①]. ByteBuffer.allocate와 allocateDirect의 차이는?

> `allocate(N)`: Heap의 byte[]를 가진 HeapByteBuffer. GC 대상. TLAB에서 빠르게 할당.
> `allocateDirect(N)`: Heap 밖 native + Heap의 작은 DirectByteBuffer 객체. Cleaner로 해제. malloc 비싸지만 I/O 시 zero-copy.
> 기준: 작고 단명 → Heap, 크고 장명 + I/O → Direct.

**🪝 Q1-1: Zero-copy가 무엇이고 왜 Direct에서만 가능한가요?**
> 일반 file read: 디스크 → 커널 page cache → JVM Heap (2번 복사). Direct Buffer + Channel.read: 디스크 → Direct Buffer (1번, DMA). Heap Buffer는 GC가 객체를 옮길 수 있어 커널이 직접 그 주소를 못 씀 — JVM이 syscall 직전 임시 Direct Buffer로 복사 후 syscall. Direct는 native 주소 고정.

### Q2 [가지 ③]. Cleaner는 무엇이고 어떻게 동작하나요?

> PhantomReference 기반 자동 해제. ① DirectByteBuffer 생성 시 Cleaner.create(buf, deallocator) 등록. ② buf unreachable → GC 처리 → Cleaner를 ReferenceQueue에 enqueue. ③ Reference Handler thread가 queue 모니터링 → Cleaner.clean() 호출 → deallocator.run() → UNSAFE.freeMemory(address). 한계: GC와 native free 사이 지연. 짧은 시간 폭주 시 OOM.

**🪝 Q2-1: Cleaner와 finalize의 차이는?**
> finalize: 객체에 finalize 메서드 정의, GC가 객체 회수 전 호출, 비결정적 + 성능 + 보안 위험 (JDK 9+ deprecated). Cleaner: PhantomReference 기반 객체 GC 후 별도 thread, 객체-cleanup 분리(인스턴스 누수 위험 ↓), 표준화된 API (`java.lang.ref.Cleaner`).

### Q3 [가지 ②]. `OutOfMemoryError: Direct buffer memory`가 발생하는 메커니즘?

> Bits.reserveMemory에서 검사:
> 1. 새 할당 + 현재 사용량 > MaxDirectMemorySize?
> 2. 그렇다면 System.gc() + Reference 처리 강제.
> 3. 9번까지 sleep 후 재시도.
> 4. 그래도 안 되면 OOM throw.
> 함정: **`-XX:+DisableExplicitGC` 켜면 System.gc()가 무력화 → 같은 워크로드에서 OOM 더 쉽게**. NIO 앱에서는 절대 켜지 말 것.

**🪝 Q3-1: MaxDirectMemorySize 기본값은?**
> 명시 안 하면 **-Xmx와 비슷** (Runtime.maxMemory() 기반). 즉 -Xmx 2g면 Direct도 최대 2g까지 → Heap과 합치면 컨테이너 limit 초과 가능. Container 환경에서는 명시 권장: `-Xmx2g -XX:MaxDirectMemorySize=512m`.

### Q4 [가지 ④]. MappedByteBuffer와 DirectByteBuffer의 차이는?

> DirectByteBuffer: malloc된 anonymous native memory, 프로세스 종료 시 사라짐, -XX:MaxDirectMemorySize 카운트.
> MappedByteBuffer: mmap된 파일 매핑, 메모리-디스크 동기, OS page cache 사용, **MaxDirectMemorySize에 카운트 안 됨**.
> 용도: Direct는 네트워크 I/O, Mapped는 큰 파일 random access (DB, log).

**🪝 Q4-1: MappedByteBuffer는 어떻게 해제하나요?**
> 표준 API 없음 (보안 + 복잡도). 옵션: ① null로 두고 GC 기다림(비결정적), ② Internal API `Unsafe.invokeCleaner(buf)` (JDK 17+ Strong Encapsulation 제약), ③ **JDK 22+ Foreign Memory API의 Arena.ofConfined()로 deterministic 해제**, ④ 작은 단위 분할 매핑.

### Q5 [가지 ①]. Netty가 Direct Buffer를 풀링하는 이유는?

> Direct Buffer 할당/해제 비용: 할당은 UNSAFE.allocateMemory ~수 us (Heap TLAB의 1000배). 해제는 Cleaner를 통한 비결정적 free. Connection 수만 대 + 매 패킷 ByteBuf 생성/해제 → 비용 폭주. Netty PooledByteBufAllocator: 16MB Chunk 단위 OS 할당, Chunk를 SubPage로 분할, release()로 풀에 반환. 결과: malloc/free 최소화, TLB pressure ↓. 단점: 풀 idle 시에도 메모리 점유, release 누락 시 chunk 계속 추가.

**🪝 Q5-1: Netty 누수를 어떻게 진단하나요?**
> `-Dio.netty.leakDetection.level=PARANOID` JVM 옵션. 100% 추적(운영에선 느림), 누수 발견 시 stack trace. 개발/staging은 PARANOID, production은 SIMPLE (1% 샘플). 출력: `LEAK: ByteBuf.release() was not called before ... at io.netty.buffer.AbstractByteBufAllocator.directBuffer(...)`.

### Q6 (Killer) [가지 ⑤]. -Xmx 2g인데 컨테이너 5GB limit에서 OOM-killed. Heap dump는 정상. 진단?

> Heap이 원인 아님 — 다른 native 영역의 합이 5GB 초과.
> 단계:
> 1. **NMT summary**: Heap 2GB + Metaspace + Threads + Code Cache + Other. Other 비정상 크면 Direct 의심.
> 2. **BufferPoolMXBean**: `direct` 또는 `mapped` pool 사용량.
> 3. **`pmap -x`**: 큰 anonymous 영역 또는 파일 매핑.
> 4. **NMT detail + Netty PARANOID**: stack trace로 caller 확인.
> 5. **JNI 의심**: NMT 합과 RSS 차이 크면 `jemalloc`/Valgrind.
> 6. **조치**: 코드 수정 + 명시적 `-XX:MaxDirectMemorySize`.

**🪝 Q6-1: 컨테이너 환경에서 메모리 분배 가이드라인?**
> 5GB limit 예시: -Xmx 2g (40%) / MaxDirectMemorySize 1g (20%) / MaxMetaspaceSize 512m (10%) / ReservedCodeCacheSize 256m / Threads 500m (500 × 1MB) / 여유 ~700m (JVM 내부, page cache, JNI). 여유분 줄이지 말 것.

### Q7 [가지 ⑥]. Foreign Memory API가 Direct Memory를 어떻게 대체하나요?

> JDK 22 JEP 454 stable. Arena + MemorySegment 모델:
> ```java
> try (Arena arena = Arena.ofConfined()) {
>     MemorySegment seg = arena.allocate(1024);
>     seg.set(ValueLayout.JAVA_INT, 0, 42);
> }  // 자동 unmap
> ```
> **deterministic free** — Cleaner의 비결정적 문제 해결. try-with-resources로 누수 방지. 새 코드는 Arena 권장. 점진적으로 DirectByteBuffer 사용 패턴이 이쪽으로 이동.

---

## 9. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 6가지 + 각 키워드 3개)
- [ ] 가지 ① WHY: Zero-copy를 그림으로 (2회 복사 vs 1회 복사) + pinning 이유
- [ ] 가지 ② WHAT: Heap의 DirectByteBuffer 객체 + Native 데이터, address 필드 연결
- [ ] 가지 ② WHAT: Bits.reserveMemory의 한계 체크 → System.gc 안전판 → OOM throw 흐름
- [ ] 가지 ③ HOW: PhantomReference 기반 두 단계 해제, 세 스레드 협력
- [ ] 가지 ④ Mapped: mmap vs malloc, OS page cache, MaxDirectMemorySize에 카운트 안 됨
- [ ] 가지 ⑤ 운영: 누수 5대 패턴
- [ ] 가지 ⑤ 운영: Container OOM-killed + Heap 정상 시나리오 6단계 진단
- [ ] 가지 ⑤ 운영: 5GB limit 메모리 분배 가이드라인
- [ ] 가지 ⑥ 진화: JDK 1.4 NIO → JDK 9 java.lang.ref.Cleaner → JDK 22 Foreign Memory
- [ ] `-XX:+DisableExplicitGC`가 NIO 앱에서 위험한 이유 설명
- [ ] 8장 꼬리질문 7개에 막힘없이 답한다

---

## 다음 단계

- → [06. GC bookkeeping](./06-gc-bookkeeping-and-others.md): Card Table, RSet, Mark Bitmap
- ← [04. Code Cache](./04-code-cache.md): JIT 결과 저장소
- ← [03. Stack & PC & Native](./03-stack-pc-native.md): Per-thread 메모리
- ← [02. Metaspace](./02-metaspace-and-class-space.md): Class 메타데이터
- ← [01. Heap & TLAB](./01-heap-and-tlab.md): Heap의 세대 구조

## 참고

- **JEP 454 Foreign Function & Memory API**: https://openjdk.org/jeps/454
- **`java.lang.ref.Cleaner` (JDK 9+)**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ref/Cleaner.html
- **`java.nio.Bits`** (소스): https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/java/nio/Bits.java
- **HotSpot `unsafe.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/prims/unsafe.cpp
- **Netty PooledByteBufAllocator**: https://github.com/netty/netty/blob/4.1/buffer/src/main/java/io/netty/buffer/PooledByteBufAllocator.java
- **Netty Leak Detection Guide**: https://netty.io/wiki/reference-counted-objects.html
- **Linux mmap(2)**: `man 2 mmap`
- **Aleksey Shipilëv — Direct Memory Internals**: https://shipilev.net/jvm/anatomy-quarks/
