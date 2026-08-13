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
  doc,
) = {
  // フォント設定
  set text(font: ("Yu Gothic", "Meiryo", "Arial"), size: 18pt)
  
  // Graphviz
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
  
  show raw.where(lang: "dot"): it => align(center)[#render-graph(it.text)]
  show raw.where(lang: "graphviz"): it => align(center)[#render-graph(it.text)]
  
  // ページ設定
  set page(
    paper: paper_size,
    margin: (x: 2cm, y: 1.5cm),
    header: none,
    footer: align(right)[#text(16pt, fill: luma(100))[#context counter(page).display("1")]]
  )
  
  // 表紙（cover: false のときは出さず、Markdown側のタイトルスライドに任せる）
  if cover and title != none {
    align(center + horizon)[
      #text(44pt, weight: "bold", fill: rgb("#003366"))[#title]
      #v(2em)
      #text(28pt)[#subtitle]
      #v(3em)
      #text(20pt)[#author]
    ]
    pagebreak()
  }
  
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
