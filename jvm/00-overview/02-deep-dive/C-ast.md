# 부록 C — AST 자료구조 (Abstract Syntax Tree)

> **본문**: [02. 컴파일 흐름 — Stage 1.2 Parsing](../02-class-compilation-flow.md#stage-1--javac-java--bytecode-4단계-분해)에서 "Parser가 토큰을 AST로 만든다"고만 했다. 여기선 **AST가 정확히 뭔지, 왜 트리인지, 왜 javac만이 아니라 모든 코드 도구가 AST를 쓰는지** 본다.

> 한 줄 정의: **AST = Abstract Syntax Tree (추상 구문 트리). 소스 코드를 트리 구조로 표현한 것**. 컴파일러가 "코드를 이해하기 위해 가장 먼저 만드는 자료구조".

---

## 1. 직관 — 식 `(1 + 2) * 3`을 트리로 그리면

소스코드:
```
(1 + 2) * 3
```

AST:
```
       *
      / \
     +   3
    / \
   1   2
```

각 노드는 **하나의 연산 또는 값**. 루트부터 깊이우선으로 평가하면:
1. `1 + 2` → 3
2. `3 * 3` → 9

이게 AST의 본질. **"이 코드를 어떻게 실행할지"가 트리 구조에 그대로 박혀 있다**.

---

## 2. 자바 한 줄을 AST로 그리면

소스:
```java
int c = a + b;
```

AST (단순화):
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

각 노드의 역할:
- `VariableDeclaration` — "변수 선언이라는 종류의 문장이다"
- `Type` — "타입 부분이 여기"
- `BinaryOp(+)` — "이항 연산자 +"
- `Identifier` — "변수 이름 참조"

**중요한 포인트**: AST에는 **공백, 줄바꿈, 괄호, 세미콜론 같은 "문법용 토큰"이 사라져 있다**. 의미에 필요한 정보만 남음. 그래서 "**Abstract** Syntax Tree" — "추상" 구문 트리다.

> 반대 개념: **Concrete Syntax Tree (CST) = Parse Tree**는 모든 토큰을 그대로 담음. AST는 그걸 정리한 결과.

---

## 3. 왜 트리인가 — 다른 자료구조로는 안 되는 이유

### 코드 자체가 본질적으로 "중첩(nested)" 구조

`int c = a + b * 3;` 한 줄도 평탄(linear)하지 않다.

```
대입문
 └─ 좌변: 변수 선언
 └─ 우변: 덧셈
          └─ 좌: a
          └─ 우: 곱셈        ← 곱셈이 덧셈 안에 들어가야 함 (precedence)
                 └─ b
                 └─ 3
```

**Lexer 출력(`["int","c","=","a","+","b","*","3",";"]`)은 1차원**이라 "`*`가 `+`보다 먼저 묶인다"는 정보가 사라져 있다. 이걸 살리려면 **계층(층위)을 가진 자료구조**가 필요한데, 계층 = 트리다.

### 문법(grammar) 자체가 재귀적

자바는 **context-free grammar(CFG)** 로 정의돼 있다. CFG의 생성 규칙은 본질적으로 재귀:

```
Expression  → Expression "+" Expression
            | Expression "*" Expression
            | Identifier
            | Number
Statement   → "if" "(" Expression ")" Statement
            | Block
Block       → "{" Statement* "}"
```

"Statement 안에 Statement가 또 들어갈 수 있다" — 이 재귀를 자료구조로 표현하면 **노드가 자기 자식으로 같은 종류의 노드를 가질 수 있는 구조**, 즉 트리가 유일한 자연스러운 답이다. **CFG → parse tree 는 형식언어 이론에서 정의 그 자체**.

### 다른 후보들과 왜 졌나

| 후보 | 왜 안 쓰나 |
|---|---|
| **토큰 리스트 그대로** | 1차원이라 precedence/중첩 표현 불가 |
| **CST(Concrete Syntax Tree)** | 괄호·세미콜론·공백까지 다 노드로 들고 있어서 너무 무겁다. 의미에 필요 없는 노드가 90%. AST는 이걸 정리한 것 |
| **Bytecode 바로** | 타입정보 없음, Lombok 같은 변환 불가, 에러 메시지 빈약, 백엔드 교체 불가 |
| **CFG(Control-Flow Graph)** | 흐름 분석엔 좋지만 **소스의 구조 정보(블록 중첩, 어노테이션 위치)가 소실**됨. CFG는 보통 AST → bytecode → JIT 단계에서 따로 만든다 |

---

## 4. AST가 어디서 만들어지나 — 컴파일 파이프라인 안에서

```
.java 소스
   ↓
1. Lexer (Token화)        ← 글자 → 토큰 시퀀스: ["int", "c", "=", "a", "+", "b", ";"]
   ↓
2. Parser (AST 생성)       ← 토큰 시퀀스 → AST (트리)
   ↓
3. Annotation Processor    ← AST를 보고 코드 생성/변환
   ↓
4. Semantic Analysis       ← AST에 타입 정보 부착
   ↓
5. Bytecode Generation     ← AST → bytecode
   ↓
.class
```

**AST는 Parser의 산출물**이고, 그 뒤 모든 단계가 AST를 입력으로 받는다. **Lombok이 `@Getter`로 메서드를 "삽입"한다는 게 정확히 AST 단계에서 일어나는 일** — getter 메서드 노드를 AST에 새 가지로 붙여넣는 것.

---

## 5. AST vs Bytecode — 두 IR의 차이

JVM 세계엔 **코드를 표현하는 IR(Intermediate Representation, 중간 표현)이 여러 층** 있다:

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

같은 식이지만 **표현이 완전히 다르다**. AST는 구조를 보존, bytecode는 실행 순서를 보존.

---

## 6. 트리여야 그 뒤 단계들이 다 굴러간다

| 단계 | AST가 트리여야 가능한 이유 |
|---|---|
| **타입 검사** | "이 `+` 노드의 좌/우 자식 타입이 호환되나?"를 재귀로 내려가며 검사 |
| **스코프 해석** | "이 `Identifier "a"`는 어느 블록의 변수냐?"를 부모 체인 거슬러 찾음 |
| **Annotation Processing (Lombok)** | `@Getter` 만나면 클래스 노드의 자식으로 메서드 노드를 **add** — 트리니까 가능 |
| **에러 메시지** | "8번째 토큰에서 오류"가 아니라 "메서드 `foo()`의 `if` 블록 안 `b` 변수가 미정의" 라고 말할 수 있음 |
| **Bytecode 생성** | 트리를 깊이우선으로 내려가며 명령어를 emit (visitor pattern) |

만약 AST 대신 **선형 IR**(예: bytecode)을 Parser가 바로 뱉으면, 위 작업들이 **선형 배열에서 패턴 매칭/오프셋 재계산**으로 바뀌어 끔찍하게 비싸진다.

---

## 7. 그래서 Truffle이 "AST를 직접 JIT한다"는 게 왜 충격적인가

**일반적인 JVM 흐름**:
```
.java → AST → bytecode → 인터프리터로 실행 + 핫코드는 bytecode를 JIT으로 native 변환
                ↑
                AST는 javac에서 한 번 만들고 버림. 런타임엔 안 봄.
```

**Truffle의 흐름**:
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

왜 충격적인가:
- **JVM 표준 모델은 bytecode가 IR**. AST는 javac 안에서만 살고 죽는다
- **Truffle은 bytecode를 안 만든다**. AST를 IR로 그대로 쓴다
- **AST 노드 하나가 "자기 자신을 어떻게 실행할지"를 들고 있음** — 노드 = 인터프리터의 한 명령
- **트리 구조가 보존돼 있어서** "이 if 노드의 조건이 99% true다" 같은 정보를 노드에 직접 붙이고, 그걸 보고 통째로 JIT 가능

> 비유: 일반 JVM이 **"책을 줄거리로 요약해서(bytecode) 읽는 것"** 이라면, Truffle은 **"책의 목차 트리를 그대로 들고 다니면서 챕터별로 실행하는 것"**. 요약을 안 하니까 정보 손실이 없고, 챕터별 통계도 그 자리에서 매길 수 있다.

---

## 8. 친숙한 예시 — AST는 어디에나 있다

| 도구 | AST를 어떻게 쓰나 |
|---|---|
| **javac** | 파싱 결과로 AST 만들고, 어노테이션 프로세싱·타입 검사·bytecode 생성에 사용 |
| **Lombok / MapStruct** | javac AST에 노드를 직접 삽입/수정해서 코드 생성 |
| **IntelliJ / Eclipse** | 코드 인덱싱, 리팩토링(rename, extract method), inspections 전부 AST 기반 |
| **ESLint / Prettier** | JS AST를 만들어서 룰 검사 + 재포매팅 |
| **Babel / TypeScript** | AST를 변환해서 ES5/ES6 트랜스파일 |
| **Roslyn (C#)** | AST 자체가 공개 API. C# 코드를 프로그래밍으로 분석/생성 |
| **Tree-sitter** | 에디터용 빠른 AST 파서. GitHub의 syntax highlighting이 이걸로 |
| **SonarQube / Checkstyle / SpotBugs** | AST를 순회하면서 룰 검사 |

> 즉 **"코드를 코드로 다루는 모든 도구"의 출발점이 AST**. IDE의 리팩토링이 작동하는 이유, Lombok이 마법처럼 getter를 만드는 이유, ESLint가 룰을 검사하는 이유 — 다 AST를 손대기 때문.

---

## 한 줄 요약

> **AST = "코드를 트리로 표현한 것"**.
> - **Parser**가 텍스트를 받아 AST를 만들고,
> - **컴파일러**(javac)는 AST를 bytecode로 변환하면서 AST를 버린다.
> - 하지만 **Truffle**은 bytecode를 안 만들고 **AST를 IR로 평생 들고 다니면서 JIT한다** — 그래서 "AST 자체가 인터프리터이자 IR"이라는 말이 나온 것.

---

## IR 한 줄 보충

**IR = Intermediate Representation (중간 표현)**. 컴파일러/런타임이 "소스 코드"와 "기계가 실제로 실행할 형태" 사이에 두는 중간 단계 표현. JVM은 **AST(컴파일러용) → bytecode(표준/배포용) → JIT IR(최적화용) → native code** 의 4단 IR 구조.

---

## 관련 부록

- [부록 A — 인터프리터 구현 4가지 방식](./A-interpreter-implementations.md): (4) AST 인터프리터(Truffle)의 본격 설명
- [부록 B — JVM 구현체 비교](./B-jvm-implementations.md): GraalVM Truffle 모드
- [부록 D — opcode 디스패치](./D-opcode-dispatch.md): bytecode가 어떻게 1차원 명령어 시퀀스가 되는가
