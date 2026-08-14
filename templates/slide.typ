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

// 幅・高さいずれかが利用可能領域をはみ出す場合だけ、縦横比を保って自動縮小する
// （mermaidなど事前レンダリング済み画像用。正方形に近い図は幅基準だけだと高さが溢れるため、
// 幅・高さ両方の縮小率を計算し、小さい方（より厳しい制約）を採用する）。
// 【注意】layout()が返すsize.heightは「ページの残りスペース」ではなく「コンテナ全体の高さ」を
// 返すため、見出しや説明文がすでに使った分は考慮されない。動的計算は信頼できないため、
// タイトル・本文の余地を見込んだ固定の高さ上限(MAX_IMG_HEIGHT)を安全側に設定する。
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
  paper_size: "presentation-16-9",
  landscape: true,
  cover: true,
  cover_page_number: true,
  graphviz: true,
  doc,
) = {
  // フォント設定（CJKフォントは build.py が取得・キャッシュした Noto Sans JP を --font-path 経由で渡す。
  // OSフォントは直接指定しない。Noto Sans JP に無いグリフはTypstが自動でシステムフォントにフォールバックする）
  set text(font: "Noto Sans JP", size: 18pt)

  // Graphviz。graphviz: false のときは既定のraw表示（素のコード表示）にフォールバックする。
  // showルール自体は常時登録する（ブロックスコープで閉じるため、ifの中で宣言すると効かなくなる）。
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

  let page-number-footer = align(right)[#text(16pt, fill: luma(100))[#context counter(page).display("1")]]

  // 表紙（cover: false のときは出さず、Markdown側のタイトルスライドに任せる）
  // 表紙だけページ番号表示を切り替えたいので、本文とは別に一時的な set page で囲む
  // （Typstの set は現在のブロックを抜けると元に戻るため、表紙用ページ設定を本文へ漏らさず適用できる）
  if cover and title != none {
    set page(
      paper: paper_size,
      margin: (x: 2cm, y: 1.5cm),
      header: none,
      footer: if cover_page_number { page-number-footer } else { none }
    )
    align(center + horizon)[
      #text(44pt, weight: "bold", fill: rgb("#003366"))[#title]
      #v(2em)
      #text(28pt)[#subtitle]
      #v(3em)
      #text(20pt)[#author]
    ]
    pagebreak()
  }

  // 本文のページ設定（ページ番号は常に表示）。ヘッダーは既定では無し（Marpのheader
  // ディレクティブがあるときだけ表示する）。フッターはfooterディレクティブが無ければ
  // 従来どおりページ番号のみ、あるときは左にfooterテキスト・右にページ番号を出す。
  set page(
    paper: paper_size,
    margin: (x: 2cm, y: 1.5cm),
    header: context {
      let marp-header = cc-marp-header.get()
      if marp-header != none {
        align(right)[#text(14pt, fill: luma(120))[#marp-header]]
      } else {
        none
      }
    },
    footer: context {
      let marp-footer = cc-marp-footer.get()
      let show-num = cc-marp-paginate.get()
      if marp-footer == none {
        if show-num { page-number-footer } else { [] }
      } else {
        grid(
          columns: (1fr, auto),
          align(left)[#text(14pt, fill: luma(120))[#marp-footer]],
          if show-num { align(right)[#text(16pt, fill: luma(100))[#counter(page).display("1")]] } else { [] }
        )
      }
    }
  )

  // 本文の設定
  set par(justify: true, leading: 1.2em)
  
  // H1 (実は使用しない想定だが念のため)
  show heading.where(level: 1): it => {
    align(center)[#text(36pt, weight: "bold")[#it.body]]
    v(1.5em)
  }
  
  // H2をスライドタイトルとして扱う
  show heading.where(level: 2): it => {
    text(24pt, weight: "bold", fill: rgb("#003366"))[#it.body]
    v(0.5em)
    line(length: 100%, stroke: 2pt + rgb("#003366"))
    v(1em)
  }

  // ブロッククオートのスタイル
  show quote.where(block: true): it => rect(
    fill: luma(245),
    stroke: (left: 4pt + rgb("#003366")),
    inset: 1em,
    width: 100%
  )[#it.body]
  
  doc
}
