export default function BookshelfScreen() {
  return (
    <section className="bookshelf-panel" aria-label="知识书架与考核文档">
      <div className="bookshelf-heading">
        <div>
          <h1>知识书架</h1>
          <p className="bookshelf-description">
            08 文档导航QA · 实现位置、测试与修复记录、当前进度
          </p>
        </div>
        <a
          href="/bookshelf/index.html#group/7"
          target="_blank"
          rel="noreferrer"
        >
          独立窗口阅读 ↗
        </a>
      </div>
      <iframe
        className="bookshelf-frame"
        title="知识书架 · 08 文档导航QA"
        src="/bookshelf/index.html#group/7"
      />
    </section>
  )
}
