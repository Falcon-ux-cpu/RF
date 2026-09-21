import json
import os
import smtplib
import bs4
import cloudscraper
import feedparser

# Настройки
RSS_URL = "https://www.azathabar.com/api/z-$g_eqvi-q_t"
SENT_LOG_FILE = "sent_articles.json"

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")

# Инициализация scraper для обхода Cloudflare/WAF
scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    }
)


def load_sent_articles():
    """Загружает список ранее отправленных ссылок."""
    if os.path.exists(SENT_LOG_FILE):
        try:
            with open(SENT_LOG_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception as e:
            print(f"Ошибка чтения {SENT_LOG_FILE}: {e}")
    return set()


def save_sent_articles(sent_set):
    """Сохраняет список отправленных ссылок."""
    try:
        with open(SENT_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(list(sent_set), f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения {SENT_LOG_FILE}: {e}")


def get_latest_articles():
    """Скачивает RSS через cloudscraper и разбирает его с помощью feedparser."""
    try:
        response = scraper.get(RSS_URL, timeout=20)
        response.raise_for_status()

        # Разбираем RSS из текста ответа
        feed = feedparser.parse(response.text)

        articles = []
        for entry in feed.entries:
            title = entry.get("title")
            link = entry.get("link")
            if title and link:
                articles.append((title, link))
        return articles
    except Exception as e:
        print(f"Ошибка при чтении RSS: {e}")
        return []


def parse_article_content(url):
    """Парсит HTML-контент статьи."""
    try:
        response = scraper.get(url, timeout=20)
        response.raise_for_status()

        soup = bs4.BeautifulSoup(response.content, "html.parser")
        article_body = soup.find("div", class_="wsw") or soup.find("article")

        if not article_body:
            return "<p>Не удалось извлечь текст статьи.</p>"

        for unneeded in article_body.find_all(["script", "style", "iframe", "form"]):
            unneeded.decompose()

        return str(article_body)
    except Exception as e:
        print(f"Ошибка при парсинге страницы {url}: {e}")
        return "<p>Ошибка при загрузке содержимого статьи.</p>"


def send_email(subject, html_body, article_url):
    """Отправляет письмо с оригинальным HTML-содержимым."""
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"FR"
    msg["From"] = GMAIL_USER
    msg["To"] = RECIPIENT_EMAIL

    email_content = f"""
    <html>
      <body>
        <p style="font-size: 12px; color: #666;">
            Оригинал статьи: <a href="{article_url}">{article_url}</a>
        </p>
        <hr>
        {html_body}
      </body>
    </html>
    """

    msg.attach(MIMEText(email_content, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_PASSWORD)
        server.send_message(msg)

    print(f"Отправлено: {subject}")


def main():
    sent_articles = load_sent_articles()
    articles = get_latest_articles()

    if not articles:
        print("Статьи не найдены или возникла ошибка при запросе RSS.")
        return

    new_sent_count = 0
    # Проходим по статьям в обратном порядке (от старых к новым)
    for title, link in reversed(articles):
        if link in sent_articles:
            continue

        print(f"Обработка новой статьи: {title} ({link})")
        content_html = parse_article_content(link)
        send_email(title, content_html, link)

        sent_articles.add(link)
        new_sent_count += 1

    if new_sent_count > 0:
        save_sent_articles(sent_articles)
        print(f"Успешно обработано новых статей: {new_sent_count}")
    else:
        print("Новых статей нет.")


if __name__ == "__main__":
    main()
            
