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

// 本文ページのヘッダー・フッター（#42）。chapters[]/front-matterによるチャプター単位の上書きは
// build.py側が章ごとに#set page(header: render-header(...), footer: render-footer(...))を
// 再発行する形で実現する（state()は使わない。#16の反省点。landscape/paper_sizeと同じ
// 「明示指定を都度出し直す」パターンで、チャプターの並べ替えに対して安全）。
#let render-header(header_text) = align(right)[
  #text(8pt, fill: luma(100))[#header_text]
  #v(0.5em)
  #line(length: 100%, stroke: 0.5pt + luma(200))
]

#let render-footer(footer_text, paginate) = {
  let page-num = context counter(page).display("1")
  if footer_text != none and paginate {
    grid(
      columns: (1fr, 1fr),
      align(left)[#text(9pt)[#footer_text]],
      align(right)[#text(9pt)[#page-num]],
    )
  } else if footer_text != none {
    align(left)[#text(9pt)[#footer_text]]
  } else if paginate {
    align(center)[#text(9pt)[#page-num]]
  } else {
    none
  }
}

#let conf(
  title: none,
  subtitle: none,
  author: none,
  date: none,
  paper_size: "a4",
  landscape: false,
  cover: true,
  cover_page_number: false,
  toc: true,
  graphviz: true,
  header: none,
  footer: none,
  paginate: true,
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
  // 2. 目次 (Table of Contents) : toc: false のときは省略する
  // -------------------------
  if toc {
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
  }

  // -------------------------
  // 3. 本文 (Body)
  // -------------------------
  set page(
    paper: paper_size,
    flipped: landscape,
    header: render-header(if header != none { header } else { title }),
    footer: render-footer(footer, paginate),
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
