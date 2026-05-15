# 00-01. Why OOP Exists — 절차지향의 한계와 OOP의 등장

> 1960년대 후반, 프로그램이 커지면서 발견된 패턴: **데이터와 함수가 분리되어 있으면 한 곳의 변경이 다른 모든 곳에 전파된다**.
> Simula 67이 첫 답을 냈다 — 데이터와 그 데이터를 처리하는 함수를 한 단위(객체)로 묶는다. 이게 OOP의 시작.

## 📍 학습 목표

1. **절차지향의 한계** — 데이터/함수 분리가 만드는 의존성 폭발 문제.
2. **OOP의 본질적 답** — 자율 객체로 책임을 캡슐화.
3. **Simula 67 → Smalltalk** 진화 — 메시지 모델로의 추상화.
4. **"객체보다 메시지가 먼저"** Alan Kay의 통찰.
5. 운영 관점: 레거시 절차지향 코드의 함정 패턴.

## 🧠 절차지향의 본질적 한계

### 예시: 도서관 시스템 (절차지향)

```c
// C 스타일 절차지향
typedef struct {
    char title[100];
    int copies;
    int borrowed;
} Book;

typedef struct {
    char name[50];
    Book* borrowed_books[10];
    int count;
} Member;

void borrow_book(Member* m, Book* b) {
    if (b->copies > b->borrowed && m->count < 10) {
        b->borrowed++;
        m->borrowed_books[m->count++] = b;
    }
}

void return_book(Member* m, Book* b) {
    b->borrowed--;
    // m->borrowed_books에서 제거 (복잡)
}
```

**문제점**:
1. **데이터/함수 분리**: `Book`은 데이터, `borrow_book`은 외부 함수.
2. **invariant 강제 어려움**: 누가 `b->borrowed`를 직접 ++해도 막을 방법 없음.
3. **변경 전파**: `Book`에 `due_date` 필드 추가 → 모든 함수 시그니처 수정.
4. **재사용 어려움**: 다른 시스템에서 `Book`만 가져가도 함수들 따로.

### OOP로 같은 시스템

```java
class Book {
    private int copies;
    private int borrowed;
    
    public boolean borrow() {   // ← Book 자기 책임
        if (borrowed >= copies) return false;
        borrowed++;
        return true;
    }
    
    public void giveBack() {
        borrowed--;
    }
}

class Member {
    private List<Book> borrowedBooks = new ArrayList<>();
    
    public boolean borrow(Book book) {
        if (borrowedBooks.size() >= 10) return false;
        if (book.borrow()) {       // ← Book에게 메시지 보냄
            borrowedBooks.add(book);
            return true;
        }
        return false;
    }
}
```

**OOP의 답**:
1. **자율 객체**: `Book.borrow()` — Book이 자기 borrowed 카운터 관리.
2. **캡슐화**: `private` 필드 — 외부에서 직접 접근 불가.
3. **메시지**: `book.borrow()` — Member가 Book에게 "빌려달라" 요청.
4. **변경 격리**: due_date 추가는 Book 안에서만.

## 🌊 OOP 등장의 시대적 동기

### 1960s 위기

- 프로그램 크기 폭발 (수만 줄 → 수십만 줄).
- 데이터 구조 변경이 함수 수백 개에 영향.
- 디버깅 시간이 작성 시간을 초과.
- "Software crisis" — NATO 컨퍼런스 1968.

### Simula 67 (Dahl & Nygaard)

- 노르웨이 컴퓨터 센터에서 시뮬레이션 프로그램용 언어.
- **"객체" 개념 첫 도입** — 데이터 + 동작 묶기.
- 클래스, 상속, 가상 메서드 (다형성).
- Stroustrup이 C++ 만들 때 영감.

### Smalltalk-72/80 (Alan Kay, Xerox PARC)

- "**메시지**가 OOP의 본질" — Kay의 후일담.
- 생물 세포 모델 영감 — 세포(객체)들이 신호(메시지)로 소통.
- 모든 것이 객체 (숫자도 객체).
- 강한 캡슐화 (외부에서 internal 못 봄).

### "객체보다 메시지가 먼저"

Alan Kay 인용:
> "I'm sorry that long ago I coined the term 'objects' for this topic because it gets many people to focus on the lesser idea. The big idea is 'messaging'."

해석:
- **메시지 = 객체 간 인터페이스**.
- 좋은 OOP 설계는 "어떤 메시지를 누가 받을까"를 먼저 결정.
- 클래스 다이어그램보다 시퀀스 다이어그램 + CRC 카드가 먼저.

## 🔬 절차지향이 못 푸는 문제 3가지

### 1. 데이터 무결성 (Invariant)

```c
// 절차지향: 누구나 b->borrowed = -1 가능
struct Book b;
b.borrowed = -1;   // 무결성 깨짐
```

OOP는 `private` + 메서드로 invariant 강제.

### 2. 다형성

```c
// 절차지향에서 "동물이 운다"
void make_sound(Animal* a) {
    if (a->type == DOG) printf("멍");
    else if (a->type == CAT) printf("야옹");
    else if (a->type == COW) printf("음매");
    // ★ 새 동물 추가 시 모든 if-else 수정
}
```

OOP의 답:
```java
abstract class Animal {
    abstract void makeSound();
}
class Dog extends Animal { void makeSound() { print("멍"); } }
class Cat extends Animal { void makeSound() { print("야옹"); } }
// 새 동물 추가는 새 class만 — 기존 코드 변경 없음 (OCP)
```

### 3. 재사용

절차지향: 데이터 구조 + 함수 묶음. 변경 시 둘 다 손봐야.
OOP: 객체 단위 재사용. 인터페이스 같으면 구현 교체 가능.

## 📊 OOP가 푼 문제 vs 못 푼 문제

### 푼 것
1. ✅ 큰 시스템의 모듈화.
2. ✅ 데이터 무결성 (캡슐화).
3. ✅ 확장성 (다형성, OCP).
4. ✅ 도메인 모델링 직관성.

### 못 푼 것 (FP가 보완)
1. ❌ 동시성 (가변 상태 공유 위험).
2. ❌ 데이터 변환 chain (map/filter 어색).
3. ❌ 추론 어려움 (객체 상태 변화 추적).

→ 그래서 Java 8+에서 FP 흡수 시작.

## 🛠️ 운영 관점 — 레거시 절차지향 패턴

### Anemic Domain Model (빈혈 도메인)

```java
// Service에 모든 로직
class BookService {
    public void borrowBook(Long memberId, Long bookId) {
        Book book = repo.find(bookId);
        Member m = memberRepo.find(memberId);
        // 비즈니스 로직 모두 Service에
        if (book.getCopies() > book.getBorrowed() && m.getBooks().size() < 10) {
            book.setBorrowed(book.getBorrowed() + 1);
            m.getBooks().add(book);
        }
    }
}

class Book {
    // getter/setter만 — 데이터 컨테이너
    private int copies;
    private int borrowed;
    // ...
}
```

진단:
- Service가 비대 (수천 줄).
- Book이 "빈혈" — 데이터만 있음.
- 사실상 절차지향 + Java 클래스 syntax.

조치:
- 비즈니스 로직을 Book/Member 객체로 이양.
- Service는 객체 간 조율 + 트랜잭션 경계만.
- → 진짜 OOP 도메인 모델.

자세히는 [Chapter 20 Ops Scenarios](../20-ops-scenarios/).

## ⚔️ 꼬리질문

### Q. OOP가 절차지향보다 항상 좋나요?

> 아니. 작은 스크립트, 데이터 변환 위주는 절차지향/함수형이 더 단순.
> OOP의 가치는 **큰 시스템의 모듈화 + 도메인 모델링**.
> 작은 utility는 정적 함수 (사실상 절차지향)가 OK.

### Q. (Killer) "절차지향 = OOP의 대척점"이라는 통념을 비판하세요.

> 부분적으로 틀림.
> - OOP의 메서드 내부는 사실상 절차지향 (sequence of statements).
> - 모든 OOP는 결국 절차지향을 포함.
> - 차이는 **모듈 경계의 위치**:
>   - 절차지향: 모듈 = 함수 (작음).
>   - OOP: 모듈 = 객체 (중간).
>   - 함수형: 모듈 = 순수함수 chain (변환).
> - 좋은 OOP는 절차지향, 함수형의 좋은 점을 모두 흡수.

## 🔗 다음

- → [02. Procedural vs OOP](./02-procedural-vs-oop.md)
- → [01. Object & Collaboration](../01-object-and-collaboration/)
