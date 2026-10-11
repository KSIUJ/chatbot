import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import MarkdownText from './MarkdownText';

const render = (text: string) => renderToStaticMarkup(<MarkdownText text={text} />);

describe('MarkdownText', () => {
  it('renders emphasis, lists and tables', () => {
    const html = render('Biblioteka: **9:00-17:00**\n\n- pon-pt\n- sierpień: nieczynna\n\n| dzień | godziny |\n|---|---|\n| pon | 9-17 |');

    expect(html).toContain('<strong>9:00-17:00</strong>');
    expect(html).toContain('<li>pon-pt</li>');
    expect(html).toContain('<th');
    expect(html).toContain('>9-17</td>');
  });

  it('opens http(s) links in a new tab and drops unsafe ones', () => {
    const html = render('[strona](https://matinf.uj.edu.pl/) i [zle](javascript:alert(1)) i https://uj.edu.pl');

    expect(html).toContain('href="https://matinf.uj.edu.pl/" target="_blank" rel="noopener noreferrer"');
    expect(html).not.toContain('javascript:');
    expect(html).toContain('zle');
    // bare addresses become links too (GFM autolinks)
    expect(html).toContain('href="https://uj.edu.pl/"');
  });

  it('never renders raw HTML or loads images', () => {
    const html = render('<script>alert(1)</script><b>x</b>\n\n![plan budynku](https://evil.example/pixel.png)');

    expect(html).not.toContain('<script');
    expect(html).not.toContain('<b>');
    expect(html).not.toContain('<img');
    expect(html).toContain('[plan budynku]');
  });

  it('renders $$ math with KaTeX but leaves single dollars alone', () => {
    const html = render('Wynik: $$e^2$$, a bilet kosztuje 5$ albo $4.');

    expect(html).toContain('class="katex');
    expect(html).toContain('5$ albo $4.');
  });

  it('keeps code as code', () => {
    const html = render('Użyj `ls -la`:\n\n```bash\necho "<b>"\n```');

    expect(html).toContain('ls -la</code>');
    expect(html).toContain('<pre');
    expect(html).toContain('echo &quot;&lt;b&gt;&quot;');
  });
});
