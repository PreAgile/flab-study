# 부록 C — AST 자료구조 (Abstract Syntax Tree)

> AST = 컴파일러가 코드를 이해하기 위해 가장 먼저 만드는 자료구조. Lombok이 마법처럼 getter 만드는 이유, IDE 리팩토링이 작동하는 이유, Truffle이 "bytecode 없이 AST를 평생 들고 다니는 polyglot 런타임"인 이유 — 모두 AST 한 단어에서 출발한다.

---

## 이 문서의 사용법

본문 → [02. 컴파일 흐름](../02-class-compilation-flow.md) 가지 ②(javac 4단계)에서 진입. Parser가 만드는 AST의 정체와 그 너머의 응용.

---

## 0. 마인드맵

### 루트 한 문장 (anchor)

> **"AST는 코드를 트리로 표현한 것이고, '왜 트리여야 하나'의 답은 코드 자체가 본질적으로 nested 구조이기 때문이다. javac 안에서만 잠깐 살다 죽지만, Lombok/IDE/Truffle은 같은 AST 개념을 평생 도구로 쓴다."**

### 4개 가지

```
        [ROOT: AST = 코드의 트리 표현]
                    │
       ┌────────┬───┼────────┬────────┐
      ① WHY     ② 어디서   ③ vs Bytecode ④ 어디에나
   왜 트리?    만들어지나   두 IR의 차이   AST 있다
       │       │             │            │
       │    Parser            │         javac/
    nested  Lombok          AST=트리    Lombok/
    구조    APT 자리        Bytecode=   IDE/
    CFG     Semantic        선형         ESLint/
    재귀    Bytecode Gen    AST→Bytecode Babel/
                                        Truffle
```

### 가지별 핵심 키워드

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① WHY 트리?** | 코드 = nested | CFG는 재귀 | 토큰 리스트 = 1차원, precedence 표현 불가 |
| **② 어디서** | Parser 산출물 | APT의 입력 | Bytecode Gen의 입력 |
| **③ vs Bytecode** | AST = 트리, 휘발성 | Bytecode = 선형, .class에 영구 | 같은 식, 다른 표현 |
| **④ 어디에나** | javac, Lombok | IDE 리팩토링 | Truffle (AST를 평생 IR로) |

---

## 1. 가지 ①: WHY — 왜 트리여야 하나

### 1.1 핵심 질문

> "AST가 왜 트리인가? 토큰 리스트로 충분하지 않나?"

### 1.2 키워드 1 — 코드 자체가 본질적으로 nested

식 `(1 + 2) * 3`을 트리로 그리면:
```
       *
      / \
     +   3
    / \
   1   2
```

자바 한 줄 `int c = a + b;`:
```
        VariableDeclaration
       /        |         \
   Type       Name       Initializer
    │          │              │
   "int"      "c"         BinaryOp(+)
                          /        \
                    Identifier   Identifier
                       "a"          "b"
```

**핵심**: AST에는 공백·줄바꿈·괄호·세미콜론 같은 문법용 토큰이 사라져 있다. 의미에 필요한 정보만 → **Abstract** Syntax Tree.

> 반대 개념: **Concrete Syntax Tree (CST) = Parse Tree**는 모든 토큰을 그대로 담음. AST는 정리한 결과.

### 1.3 키워드 2 — Lexer 출력은 1차원, precedence 표현 불가

`int c = a + b * 3;` 한 줄도 평탄(linear)하지 않다:
```
대입문
 └─ 좌변: 변수 선언
 └─ 우변: 덧셈
          └─ 좌: a
          └─ 우: 곱셈        ← 곱셈이 덧셈 안에 (precedence)
                 └─ b
                 └─ 3
```

Lexer 출력(`["int","c","=","a","+","b","*","3",";"]`)은 1차원이라 "`*`가 `+`보다 먼저 묶인다"는 정보가 사라져 있다. 계층을 살리려면 트리.

### 1.4 키워드 3 — 문법(CFG)이 본질적으로 재귀

자바는 **context-free grammar (CFG)**로 정의:
```
Expression  → Expression "+" Expression
            | Expression "*" Expression
            | Identifier
            | Number
Statement   → "if" "(" Expression ")" Statement
Block       → "{" Statement* "}"
```

"Statement 안에 Statement가 또" — 이 재귀를 자료구조로 표현하면 **노드가 자기 자식으로 같은 종류의 노드를 가질 수 있는 구조** = 트리. **CFG → parse tree는 형식언어 이론에서 정의 그 자체**.

### 1.5 다른 후보들이 왜 졌나

| 후보 | 왜 안 쓰나 |
|---|---|
| **토큰 리스트 그대로** | 1차원이라 precedence/중첩 표현 불가 |
| **CST (Concrete)** | 괄호·세미콜론·공백까지 노드로 → 너무 무거움 |
| **Bytecode 바로** | 타입정보 없음, Lombok 같은 변환 불가, 에러 메시지 빈약 |
| **CFG (Control-Flow Graph)** | 흐름 분석엔 좋지만 소스 구조 정보(블록 중첩, 어노테이션 위치) 소실 |

---

## 2. 가지 ②: 어디서 만들어지나

### 2.1 핵심 질문

> "AST는 컴파일 파이프라인의 어느 자리에서 생기고 어디로 흘러가나?"

### 2.2 키워드 1 — Parser의 산출물

```
.java 소스
   ↓
1. Lexer (Token화)        ← "int", "c", "=", ...
   ↓
2. Parser (AST 생성)      ← ★ 여기서 AST가 만들어짐
   ↓
3. Annotation Processor   ← AST를 보고 코드 생성/변환
   ↓
4. Semantic Analysis      ← AST에 타입 정보 부착
   ↓
5. Bytecode Generation    ← AST → bytecode
   ↓
.class
```

**AST는 Parser의 산출물**이고, 그 뒤 모든 단계가 AST를 입력으로 받는다.

### 2.3 키워드 2 — APT(Annotation Processor)가 끼어드는 자리

**Lombok이 `@Getter`로 메서드를 "삽입"한다는 게 정확히 AST 단계에서 일어나는 일** — getter 메서드 노드를 AST에 새 가지로 붙여넣는 것.

APT가 raw 텍스트가 아닌 AST 단계에서 끼어들기 때문에:
- 새 코드 추가가 노드 add로 끝남
- 기존 코드 의미 보존
- 라운드 반복(생성된 코드를 다시 AST로 만들어 또 처리)이 자연스럽게 가능

### 2.4 키워드 3 — Bytecode Gen에서 트리 → 선형으로

Bytecode Generation은 AST를 **깊이우선 후위 순회**하면서 명령어를 emit한다 (visitor pattern). 트리니까 재귀가 자연스럽고, 각 노드가 자기 자식을 먼저 emit한 뒤 자기 자신을 emit하는 패턴.

### 2.5 트리여야 그 뒤 단계들이 다 굴러간다

| 단계 | AST가 트리여야 가능한 이유 |
|---|---|
| **타입 검사** | "이 `+` 노드의 좌/우 자식 타입이 호환되나?"를 재귀로 |
| **스코프 해석** | "이 `Identifier "a"`는 어느 블록의 변수냐?"를 부모 체인 거슬러 |
| **APT (Lombok)** | `@Getter` 만나면 클래스 노드 자식으로 메서드 노드 add — 트리니까 가능 |
| **에러 메시지** | "8번째 토큰에서 오류"가 아니라 "메서드 `foo()`의 `if` 블록 안 `b` 변수가 미정의" |
| **Bytecode 생성** | 트리를 깊이우선으로 내려가며 명령어 emit (visitor) |

만약 AST 대신 선형 IR을 Parser가 바로 뱉으면, 위 작업들이 선형 배열에서 패턴 매칭/오프셋 재계산으로 바뀌어 끔찍하게 비싸진다.

---

## 3. 가지 ③: AST vs Bytecode — 두 IR의 차이

### 3.1 핵심 질문

> "AST와 Bytecode는 둘 다 코드의 표현인데 뭐가 다른가?"

### 3.2 키워드 1 — 구조: 트리 vs 선형

JVM 세계엔 **코드를 표현하는 IR**이 여러 층:
```
.java 소스 (텍스트)
   ↓ Parser
AST (트리, 메모리 안)
   ↓ Bytecode Generator
Bytecode (선형 명령어 시퀀스, .class 파일)
   ↓ JIT
Native code (CPU 명령어)
```

| 축 | AST | Bytecode |
|---|---|---|
| **구조** | 트리 | 선형 시퀀스 (1차원 배열) |
| **추상화 레벨** | 높음 (소스에 가까움) | 낮음 (CPU에 가까움) |
| **저장 위치** | 컴파일러 메모리 (휘발성) | `.class` 파일 (디스크) |
| **수명** | 컴파일 끝나면 폐기 | 영구 |
| **수정 용이성** | 쉬움 (노드 add/remove) | 어려움 (오프셋 재계산) |
| **언어 종속** | 자바 문법에 종속 | 언어 중립 (JVM 표준) |

### 3.3 키워드 2 — 같은 식, 다른 표현

`(1 + 2) * 3`을 둘로 비교:

**AST**:
```
       *
      / \
     +   3
    / \
   1   2
```

**Bytecode**:
```
iconst_1      ; 1 push
iconst_2      ; 2 push
iadd          ; pop 두 개 더해서 push (= 3)
iconst_3      ; 3 push
imul          ; pop 두 개 곱해서 push (= 9)
```

같은 식이지만 표현이 완전히 다르다. AST는 **구조를 보존**, bytecode는 **실행 순서를 보존**.

### 3.4 키워드 3 — IR의 4단 구조

**IR = Intermediate Representation**. 컴파일러/런타임이 "소스 코드"와 "기계가 실제로 실행할 형태" 사이에 두는 중간 단계 표현. JVM은 **AST(컴파일러용) → bytecode(표준/배포용) → JIT IR(최적화용) → native code**의 4단 IR 구조.

각 IR의 책임이 다르다:
- **AST** — 의미 보존, APT/타입검사/리팩토링
- **Bytecode** — 표준화, 배포, 검증
- **JIT IR (HIR/LIR/Sea of Nodes)** — 최적화
- **Native code** — 실제 실행

---

## 4. 가지 ④: AST는 어디에나 있다 — Truffle의 충격

### 4.1 핵심 질문

> "AST는 javac 안에서만 사는 자료구조인가? 다른 도구들은?"

### 4.2 키워드 1 — 친숙한 예시들

| 도구 | AST를 어떻게 쓰나 |
|---|---|
| **javac** | 파싱 결과로 AST, APT·타입 검사·bytecode 생성에 사용 |
| **Lombok / MapStruct** | javac AST에 노드를 직접 삽입/수정해서 코드 생성 |
| **IntelliJ / Eclipse** | 코드 인덱싱, 리팩토링(rename, extract method), inspections 전부 AST 기반 |
| **ESLint / Prettier** | JS AST를 만들어서 룰 검사 + 재포매팅 |
| **Babel / TypeScript** | AST를 변환해서 ES5/ES6 트랜스파일 |
| **Roslyn (C#)** | AST 자체가 공개 API. C# 코드를 프로그래밍으로 분석/생성 |
| **Tree-sitter** | 에디터용 빠른 AST 파서. GitHub의 syntax highlighting |
| **SonarQube / Checkstyle / SpotBugs** | AST를 순회하면서 룰 검사 |

→ **"코드를 코드로 다루는 모든 도구"의 출발점이 AST**.

### 4.3 키워드 2 — Truffle의 충격 (AST를 평생 IR로)

**일반적인 JVM 흐름**:
```
.java → AST → bytecode → 인터프리터 + 핫코드 JIT
                ↑
                AST는 javac에서 한 번 만들고 버림. 런타임엔 안 봄.
```

**Truffle (GraalVM)의 흐름**:
```
.rb (Ruby 코드) → AST → AST를 트리 채로 메모리에 보존
                          ↓
                  AST 노드를 직접 인터프리트 (자식 노드 재귀 평가)
                          ↓
                  핫한 서브트리 발견 → AST를 통째로 Graal JIT으로 native 변환
                          ↓
                  가정 깨지면 다시 AST 인터프리터로 폴백

                  ※ bytecode 단계 자체가 없다
```

**왜 충격적인가**:
- JVM 표준 모델은 bytecode가 IR. AST는 javac 안에서만 살고 죽는다.
- **Truffle은 bytecode를 안 만든다**. AST를 IR로 그대로 쓴다.
- AST 노드 하나가 "자기 자신을 어떻게 실행할지"를 들고 있음 — 노드 = 인터프리터의 한 명령.
- 트리 구조가 보존돼 있어서 "이 if 노드의 조건이 99% true다" 같은 정보를 노드에 직접 붙이고, 통째로 JIT 가능.

비유: 일반 JVM이 "책을 줄거리로 요약(bytecode)해서 읽는 것"이라면, Truffle은 "책의 목차 트리를 그대로 들고 다니면서 챕터별로 실행하는 것". 요약을 안 하니까 정보 손실 없고, 챕터별 통계도 그 자리에서 매길 수 있다.

### 4.4 키워드 3 — Polyglot은 AST 위에서 가능했다

Truffle 위에서 TruffleRuby, GraalPy, GraalJS가 같은 JVM 안에서 같은 인프라를 공유. 각 언어 구현자는 **AST 인터프리터만 Java로 작성**하면 되고, JIT/GC/메모리 관리는 Graal+HotSpot이 공통으로 제공.

만약 bytecode IR을 강제했다면 각 언어가 다 자기 bytecode 포맷을 만들어야 했을 것. AST를 직접 IR로 쓴 덕에 polyglot이 가능해졌다.

---

## 5. 면접 답변 워크플로우

### 5.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 |
|---|---|
| "AST가 뭐죠?" | ① WHY |
| "왜 트리여야 하나?" | ① CFG 재귀 |
| "Lombok이 왜 작동?" | ② APT 자리 |
| "AST와 Bytecode 차이?" | ③ |
| "IR이 뭐? IR이 4단?" | ③ |
| "Truffle은 뭐가 특별?" | ④ AST IR |
| "AST 어디서 쓰나?" | ④ 친숙한 예시 |

### 5.2 답변 템플릿

> "AST는 코드를 트리로 표현한 자료구조입니다(← 루트).
> 왜 트리인가 — **코드 자체가 본질적으로 nested 구조**이고, 문법(CFG)이 재귀적으로 정의되기 때문입니다. 토큰 리스트는 1차원이라 precedence를 표현 못 합니다.
> AST는 Parser가 만들어서 APT/타입검사/Bytecode Gen이 입력으로 받습니다. **Lombok이 `@Getter` 메서드를 마법처럼 삽입할 수 있는 건 AST 단계에서 노드를 add하기 때문**입니다.
> 일반 JVM에서는 AST가 javac 안에서만 잠깐 살고 bytecode로 변환된 뒤 버려지지만, **GraalVM Truffle은 AST 자체를 IR로 평생 들고 다니면서 핫한 서브트리를 통째로 JIT**합니다 — 이 덕분에 Ruby/Python/JS 같은 polyglot이 가능해졌습니다."

---

## 6. 꼬리질문 트리

### Q1 [가지 ①]. AST는 왜 트리여야 하나?

> 코드 자체가 nested 구조(중첩) — `if` 안에 `if`, 식 안에 식. 문법(CFG)이 재귀적으로 정의되므로 자료구조도 재귀(트리)가 자연스러움. 토큰 리스트는 1차원이라 precedence/중첩 표현 불가. CST는 너무 무겁고, bytecode는 타입 정보가 빠지고, CFG는 소스 구조가 소실됨.

**🪝 Q1-1: AST와 CST(Concrete Syntax Tree) 차이?**
> CST는 모든 토큰(괄호, 세미콜론, 공백)을 노드로 보존. AST는 그걸 정리해서 의미에 필요한 노드만 남김 → "Abstract".

### Q2 [가지 ②]. Lombok이 어떻게 getter를 "마법처럼" 추가하나?

> javac의 AST 단계에 끼어들어 **클래스 노드의 자식으로 메서드 노드를 add**. 그 뒤 정상 컴파일이 진행되니 javac 입장에선 처음부터 있던 메서드와 동일. 단, 공식 API가 아닌 내부 javac AST를 직접 건드림 → IDE는 별도 Lombok 플러그인 필요.

### Q3 [가지 ④]. Truffle이 bytecode 없이 AST를 직접 JIT한다는 게 무슨 의미?

> 일반 JVM은 .java → AST → bytecode → JIT. Truffle은 .rb → AST → AST를 IR로 평생 보존 → 핫 서브트리를 통째로 JIT. bytecode 단계가 없음. 그래서 Ruby/Python/JS 같은 polyglot이 같은 인프라(Truffle + Graal) 위에서 가능해짐.

**🪝 Q3-1: AST를 평생 들고 다니면 메모리 안 큰가?**
> 큼. 그래서 AST 노드 자체를 "self-optimizing"하게 만듦 — 한 번 평가된 노드는 타입을 좁히고 specialization한 노드로 교체. 핫해지면 통째로 JIT 컴파일 → AST 인터프리터는 fallback으로만.

---

## 7. 학습 체크리스트

- [ ] AST의 정의와 "Abstract"의 의미를 설명한다
- [ ] AST가 트리여야 하는 3가지 이유(nested 구조 / CFG 재귀 / precedence)를 말한다
- [ ] AST가 컴파일 파이프라인 어디에서 만들어지고 어떻게 흘러가는지 그린다
- [ ] AST vs Bytecode 비교표를 적는다 (구조/저장/수명/수정용이성)
- [ ] IR의 4단 구조(AST → bytecode → JIT IR → native)를 말한다
- [ ] Lombok이 AST에 끼어드는 자리를 설명한다
- [ ] Truffle이 AST를 IR로 쓰는 의미와 polyglot 가능성을 설명한다

---

## 관련 부록

- [부록 A — 인터프리터 구현 4가지 방식](./A-interpreter-implementations.md): (4) AST 인터프리터(Truffle)의 본격 설명
- [부록 B — JVM 구현체 비교](./B-jvm-implementations.md): GraalVM Truffle 모드
- [부록 D — opcode 디스패치](./D-opcode-dispatch.md): bytecode가 어떻게 1차원 명령어 시퀀스가 되는가
