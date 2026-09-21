import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import bs4
import cloudscraper

# Настройки
BASE_URL = "https://www.azathabar.com"
SENT_LOG_FILE = "sent_articles.json"

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")

scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    }
)


def load_sent_articles():
    if os.path.exists(SENT_LOG_FILE):
        try:
            with open(SENT_LOG_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception as e:
            print(f"Ошибка чтения {SENT_LOG_FILE}: {e}")
    return set()


def save_sent_articles(sent_set):
    try:
        with open(SENT_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(list(sent_set), f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения {SENT_LOG_FILE}: {e}")


def get_latest_articles():
    """Парсит ссылки на статьи прямо с главной страницы."""
    try:
        response = scraper.get(BASE_URL, timeout=20)
        response.raise_for_status()

        soup = bs4.BeautifulSoup(response.content, "html.parser")
        articles = []
        seen_links = set()

        # Находим все ссылки на статьи на главной странице
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            title = a_tag.get_text(strip=True)

            # Проверяем, что ссылка ведет на новостную статью (.html) и имеет заголовок
            if href.endswith(".html") and len(title) > 10:
                full_url = href if href.startswith("http") else f"{BASE_URL}{href}"
                if full_url not in seen_links:
                    seen_links.add(full_url)
                    articles.append((title, full_url))

        return articles
    except Exception as e:
        print(f"Ошибка при парсинге главной страницы: {e}")
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
        print(f"Ошибка при парсинге статьи {url}: {e}")
        return "<p>Ошибка при загрузке содержимого статьи.</p>"


def send_email(subject, html_body, article_url):
    """Отправляет письмо с тему RF: <Заголовок>."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"RF: {subject}"
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

    print(f"Отправлено письмо с темой 'RF: {subject}'")


def main():
    sent_articles = load_sent_articles()
    articles = get_latest_articles()

    if not articles:
        print("Статьи не найдены.")
        return

    new_sent_count = 0
    # Обрабатываем от старых к новым
    for title, link in reversed(articles):
        if link in sent_articles:
            continue

        print(f"Обработка новости: {title} ({link})")
        content_html = parse_article_content(link)
        send_email(title, content_html, link)

        sent_articles.add(link)
        new_sent_count += 1

    if new_sent_count > 0:
        save_sent_articles(sent_articles)
        print(f"Обработано новых статей: {new_sent_count}")
    else:
        print("Новых статей нет.")


if __name__ == "__main__":
    main()
    
