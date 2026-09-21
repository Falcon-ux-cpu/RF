import os
import smtplib
import xml.etree.ElementTree as ET
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import bs4
import requests

# Настройки
RSS_URL = "https://www.azathabar.com/api/z-$g_eqvi-q_t"
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def get_latest_article():
    """Получает ссылку и заголовок последней статьи из RSS."""
    try:
        response = requests.get(RSS_URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        channel = root.find("channel")
        item = channel.find("item") if channel is not None else None

        if item is not None:
            title = item.find("title").text
            link = item.find("link").text
            return title, link
    except Exception as e:
        print(f"Ошибка при чтении RSS: {e}")

    return None, None


def parse_article_content(url):
    """Парсит HTML-контент статьи, сохраняя форматирование."""
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()

    soup = bs4.BeautifulSoup(response.content, "html.parser")

    # Ищем основной контейнер статьи
    article_body = soup.find("div", class_="wsw") or soup.find(
        "article"
    )

    if not article_body:
        return "<p>Не удалось вырезать основной текст статьи.</p>"

    # Удаляем ненужные элементы внутри статьи (видео-плееры, рекламу, соцсети)
    for unneeded in article_body.find_all(
        ["script", "style", "iframe", "form"]
    ):
        unneeded.decompose()

    return str(article_body)


def send_email(subject, html_body, article_url):
    """Отправляет письмо с HTML-содержимым статьи."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"FR: {subject}"
    msg["From"] = GMAIL_USER
    msg["To"] = RECIPIENT_EMAIL

    # Добавляем ссылку на оригинал в начало письма
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

    print(f"Статья successfully отправлена: {subject}")


def main():
    title, link = get_latest_article()

    if not title or not link:
        print("Статьи не найдены.")
        return

    print(f"Найдена статья: {title} ({link})")
    content_html = parse_article_content(link)
    send_email(title, content_html, link)


if __name__ == "__main__":
    main()
