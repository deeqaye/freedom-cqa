import pytest

from app.services.ingest import guess_operator


def op(*texts):
    return [{"turn": 1, "speaker": "client", "text": "Здравствуйте, меня зовут Клиентова"}] + [
        {"turn": i + 2, "speaker": "operator", "text": t} for i, t in enumerate(texts)]


@pytest.mark.parametrize("text,name", [
    ("Здравствуйте! Меня зовут Алина. Откройте «Кабинет».", "Алина"),
    ("Здравствуйте, я Тимур. Понимаю, что это беспокоит.", "Тимур"),
    ("Добрый день! Я Лера из поддержки.", "Лера"),
    ("Здравствуйте. Я Илья. Форма предоставляется на английском.", "Илья"),
    ("Hi, I'm Maya from support.", "Maya"),
    ("Hello, my name is Daniel.", "Daniel"),
    ("Сәлеметсіз бе, менің атым Аружан.", "Аружан"),
    ("Сәлеметсіз бе, мен Дана. Ақша көрінбей қалса...", "Дана"),
    ("Сәлеметсіз бе! Мен Нұрланмын. «Меню» бөлімін ашыңыз.", "Нұрлан"),
    ("Сәлеметсіз бе, мен Айбекпін.", "Айбек"),
    ("Сәлеметсіз бе! Мен Айсұлумын.", "Айсұлу"),
])
def test_names_in_three_languages(text, name):
    assert guess_operator(op(text)) == name


@pytest.mark.parametrize("texts", [
    ("Здравствуйте, фридом брокер меня зовут [Имя скрыто], чем могу помочь?",),  # masked on calls
    ("Привет, где именно ищете?",),
    ("Здравствуйте, я Вам сейчас помогу.",),           # polite pronoun is not a name
    ("Hi, I'm sorry for the wait.",),                  # lowercase word is not a name
    ("Логин мен Пароль жүйеде қалады.",),              # Kazakh "мен" = "and" mid-sentence
    ("Hello, this is Freedom Broker support.",),
])
def test_no_false_names(texts):
    assert guess_operator(op(*texts)) is None


def test_client_lines_are_ignored_and_later_intro_found():
    assert guess_operator(op("Минуту, проверяю.", "Извините, я Олег, продолжу с вами.")) == "Олег"
