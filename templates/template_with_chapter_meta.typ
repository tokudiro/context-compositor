// templates/template.typ をベースに、front-matterのtitle/subtitle/author/dateを
// そのチャプターのページに限定して反映する chapter-meta() を実装したテンプレート例（#38）。
// 文書全体の表紙（title/subtitle/author/date）は常にconfig.yaml側（conf()の引数）が正とする。
// front-matterはあくまで「そのチャプターのページ」だけに影響する、文書全体には影響しない。
//
// 実装メモ: Typstのset/showは宣言したブロックを抜けると失効するため、
// 「このチャプター以降・次のchapter-meta呼び出しまで有効」という値は素朴な if 分岐の
// set では実現できない（if内で宣言したsetは、その if ブロックを抜けたdocには効かない）。
// 代わりにstate()を使い、ヘッダーと見出しの装飾をcontext経由で反応的に読ませる。
#let cc-title = state("cc-chapter-title", none)
#let cc-subtitle = state("cc-chapter-subtitle", none)
#let cc-author = state("cc-chapter-author", none)
#let cc-date = state("cc-chapter-date", none)

// Marpディレクティブ（<!-- header: X -->等）の値。同じくstate()で反応的に読む（7章、#16）。
// headerディレクティブは、chapter-meta由来のtitleより優先してヘッダーに表示する
// （Marpディレクティブは著者が明示的にそのページ向けに書いたものであるため）。
#let cc-marp-header = state("cc-marp-header", none)
#let cc-marp-footer = state("cc-marp-footer", none)
#let cc-marp-paginate = state("cc-marp-paginate", true)

// title: build.py側で「front-matterの値、無ければ文書全体のtitle」に解決済みの前提（常に非none）。
// subtitle/author/dateはfront-matterに無ければnoneのままで、その章にバイラインを出さない。
#let chapter-meta(title: none, subtitle: none, author: none, date: none, doc) = {
  cc-title.update(title)
  cc-subtitle.update(subtitle)
  cc-author.update(author)
  cc-date.update(date)
  doc
}

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

  // 本文のヘッダーに使うtitleの既定値（chapter-metaが呼ばれるまでの間・章のfront-matterが
  // 無い場合のフォールバック）を、文書全体のtitleで初期化しておく。
  cc-title.update(title)

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
    // ヘッダーはMarpのheaderディレクティブがあればそれを優先し、無ければcc-title
    // （chapter-meta由来。#38）を表示する。
    header: context {
      let marp-header = cc-marp-header.get()
      align(right)[
        #text(8pt, fill: luma(100))[#if marp-header != none { marp-header } else { cc-title.get() }]
        #v(0.5em)
        #line(length: 100%, stroke: 0.5pt + luma(200))
      ]
    },
    // フッターはMarpのfooterディレクティブが無ければ、従来どおりページ番号だけを中央に表示する。
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

  // 見出し1 (大見出し/章) の直前で必ず改ページし、直後にその章のsubtitle/author/date
  // （chapter-metaで設定されていれば）をバイラインとして表示する。バイラインを見出しの
  // 前段の独立した内容として置くと、見出し側のpagebreak(weak: true)がバイラインだけを
  // 別ページに追いやってしまうため、見出しのshowルール自身の中で出す。
  show heading.where(level: 1): it => context {
    pagebreak(weak: true)
    v(1em)
    it
    let sub = cc-subtitle.get()
    let auth = cc-author.get()
    let dt = cc-date.get()
    if sub != none or auth != none or dt != none {
      let byline = ()
      if auth != none { byline.push(auth) }
      if dt != none { byline.push(dt) }
      block(above: 0.3em, below: 0.5em)[
        #if sub != none [
          #text(11pt, style: "italic")[#sub]
          #linebreak()
        ]
        #if byline.len() > 0 [
          #text(9pt, fill: luma(120))[#byline.join(" -- ")]
        ]
      ]
    } else {
      v(0.5em)
    }
  }

  doc
}
