// front-matterのtitle/subtitle/author/dateは、そのチャプターのページに限定して反映する
// 想定（#38）。このテンプレートは表示場所を持たないため何もしない（渡された値はそのまま無視する）。
// 実際に表示するテンプレートの例は templates/template_with_chapter_meta.typ を参照。
#let chapter-meta(title: none, subtitle: none, author: none, date: none, doc) = doc

// Marpディレクティブ（<!-- header: X -->等）の値。以降のページに適用され、次の同種
// ディレクティブまで有効（Marpと同じスコープ規則、7章、#16）。チャプター（ファイル）を
// またいで持続する必要があるため、chapter-metaと同じくstate()で反応的に読む。
#let cc-marp-header = state("cc-marp-header", none)
#let cc-marp-footer = state("cc-marp-footer", none)
#let cc-marp-paginate = state("cc-marp-paginate", true)

// 幅・高さいずれかが利用可能領域をはみ出す場合だけ、縦横比を保って自動縮小する（mermaidなど事前レンダリング済み画像用）
#let MAX_IMG_HEIGHT = 12cm
#let fit-image(path) = layout(size => context {
  let img = image(path)
  let i-size = measure(img)
  let w-scale = size.width / i-size.width
  let h-scale = MAX_IMG_HEIGHT / i-size.height
  let scale = calc.min(w-scale, h-scale, 1.0)
  if scale < 1.0 {
    image(path, width: i-size.width * scale)
  } else {
    img
  }
})

#let conf(
  title: none,
  subtitle: none,
  author: none,
  date: none,
  paper_size: "a4",
  landscape: false,
  cover: true,
  cover_page_number: false,
  graphviz: true,
  doc,
) = {
  // フォント設定（CJKフォントは build.py が取得・キャッシュした Noto Sans JP を --font-path 経由で渡す。
  // OSフォントは直接指定しない。Noto Sans JP に無いグリフはTypstが自動でシステムフォントにフォールバックする）
  set text(font: "Noto Sans JP", size: 10.5pt)

  // プラグイン: Graphviz (dot) 自動レンダリングと、はみ出し防止の自動縮小
  // graphviz: false のときは既定のraw表示（素のコード表示）にフォールバックする。
  // showルール自体は常時登録する（ifブロックの中で宣言すると、ブロックを抜けた
  // doc側には効かなくなる。show/setはブロックスコープで閉じるため）。
  import "@preview/diagraph:0.3.7": render

  let render-graph(code) = layout(size => context {
    let graph = render(code)
    let g-size = measure(graph)
    if g-size.width > size.width {
      render(code, width: 100%)
    } else {
      graph
    }
  })

  show raw.where(lang: "dot"): it => if graphviz { align(center)[#render-graph(it.text)] } else { it }
  show raw.where(lang: "graphviz"): it => if graphviz { align(center)[#render-graph(it.text)] } else { it }

  // -------------------------
  // 1. 表紙 (Cover Page) : cover: false のときは省略する
  // -------------------------
  if cover {
    set page(
      paper: "a4", flipped: false, margin: 2.5cm, header: none,
      footer: if cover_page_number { align(center)[#text(10pt)[#context counter(page).display("1")]] } else { none }
    )

    align(center + horizon)[
      #text(24pt, weight: "bold")[#title]
      #v(3em)
      #text(14pt)[#subtitle]
      #v(4em)
      #text(12pt)[#author]
      #v(1em)
      #text(12pt)[#date]
    ]
    pagebreak()
  }

  // -------------------------
  // 2. 目次 (Table of Contents)
  // -------------------------
  set page(
    paper: paper_size,
    flipped: landscape,
    margin: (x: 2cm, y: 2.5cm),
    header: none,
    footer: align(center)[#text(10pt)[- #context counter(page).display("i") -]]
  )
  counter(page).update(1) // 目次のページ番号を i から開始

  align(center)[
    #text(18pt, weight: "bold")[目次]
  ]
  v(1.5em)
  outline(title: none, indent: auto)
  pagebreak()

  // -------------------------
  // 3. 本文 (Body)
  // -------------------------
  set page(
    paper: paper_size,
    flipped: landscape,
    // ヘッダーはMarpのheaderディレクティブがあればそれを、無ければ文書全体のtitleを表示する
    header: context {
      let marp-header = cc-marp-header.get()
      align(right)[
        #text(8pt, fill: luma(100))[#if marp-header != none { marp-header } else { title }]
        #v(0.5em)
        #line(length: 100%, stroke: 0.5pt + luma(200))
      ]
    },
    // フッターはMarpのfooterディレクティブが無ければ、従来どおりページ番号だけを中央に表示する。
    // footerディレクティブがある場合のみ左にfooterテキスト・右にページ番号（paginateがtrueの間）を出す。
    footer: context {
      let marp-footer = cc-marp-footer.get()
      let show-num = cc-marp-paginate.get()
      if marp-footer == none {
        if show-num { align(center)[#text(9pt)[#counter(page).display("1")]] } else { [] }
      } else {
        grid(
          columns: (1fr, auto),
          align(left)[#text(9pt, fill: luma(120))[#marp-footer]],
          if show-num { align(right)[#text(9pt)[#counter(page).display("1")]] } else { [] }
        )
      }
    }
  )
  counter(page).update(1) // 本文のページ番号を 1 からリセット
  
  set par(justify: true, leading: 0.8em)
  
  // 見出し1 (大見出し/章) の直前で必ず改ページする（すでにページ先頭の場合はスキップ）
  show heading.where(level: 1): it => {
    pagebreak(weak: true)
    v(1em)
    it
    v(0.5em)
  }
  
  doc
}
