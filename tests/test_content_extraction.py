from app.providers.content import extract_content_from_html


def test_extract_content_prefers_jsonld_article_body():
    document = """
    <html>
      <head>
        <script type="application/ld+json">
        {
          "@type": "NewsArticle",
          "headline": "测试新闻",
          "articleBody": "这是一段来自 JSON-LD 的完整新闻正文，用于验证正文提取能力。它包含足够多的有效字符，可以作为正式正文写入数据库并参与全文检索。"
        }
        </script>
      </head>
      <body><p>页面上的其他短文本。</p></body>
    </html>
    """
    content = extract_content_from_html(document, min_chars=20)
    assert content is not None
    assert "JSON-LD" in content
    assert "全文检索" in content


def test_extract_content_falls_back_to_paragraphs_and_ignores_noise():
    document = """
    <html>
      <body>
        <nav><p>首页 新闻 财经 科技</p></nav>
        <main>
          <p>深圳人工智能产业持续发展，多个机器人项目进入规模化应用阶段。</p>
          <p>相关企业表示，新的产品将在教育、家庭陪伴和服务行业逐步落地。</p>
        </main>
        <footer><p>版权信息 联系我们 网站地图</p></footer>
      </body>
    </html>
    """
    content = extract_content_from_html(document, min_chars=30)
    assert content is not None
    assert "深圳人工智能产业" in content
    assert "家庭陪伴" in content
    assert "网站地图" not in content


def test_extract_content_rejects_too_short_pages():
    document = "<html><body><p>太短。</p></body></html>"
    assert extract_content_from_html(document, min_chars=20) is None
