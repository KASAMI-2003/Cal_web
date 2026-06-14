/**
 * 数字孪生页：使用说明、上传文件格式、晶系识别规则。
 * 与 server/digital_twin/twin_dat_probe.py、crystal_systems/ 行为对齐。
 */

const CRYSTAL_SYSTEMS: {
  id: string;
  zh: string;
  lc: string;
  moduli: string;
  phases: string;
  note: string;
}[] = [
  {
    id: 'cubic',
    zh: '立方',
    lc: 'C',
    moduli: 'BV/BR/GV/GR 四式拟合，或仅 BH/GH',
    phases: 'fcc、bcc、立方',
    note: '单晶立方；VR 四列不自洽时需改提供 c11/c12/c44',
  },
  {
    id: 'hexagonal',
    zh: '六方',
    lc: 'H',
    moduli: 'BH/GH（或 EH+ν）近似',
    phases: 'hcp、hex、六方',
    note: '5 个独立常数；有完整 c_ij 时更准确',
  },
  {
    id: 'monoclinic',
    zh: '单斜',
    lc: 'M',
    moduli: 'BH/GH + AVR（或 GV/GR）近似',
    phases: 'alpha_pp、monoclinic、单斜',
    note: '13 个独立常数；推荐表内提供 C11…C66',
  },
  {
    id: 'isotropic',
    zh: '多晶有效（各向同性）',
    lc: 'C',
    moduli: '仅 BH/GH',
    phases: '未识别相名、多晶/混合等',
    note: '曲面为球；侧栏 B/G/E 仍取 Hill 列',
  },
  {
    id: 'tetragonal',
    zh: '四方',
    lc: 'TI / TII',
    moduli: '—',
    phases: '—',
    note: '需在表中提供完整 c_ij',
  },
  {
    id: 'orthorhombic',
    zh: '正交',
    lc: 'O',
    moduli: '—',
    phases: '—',
    note: '需在表中提供完整 c_ij',
  },
  {
    id: 'trigonal',
    zh: '三方',
    lc: 'RI / RII',
    moduli: '—',
    phases: '—',
    note: '需在表中提供完整 c_ij',
  },
  {
    id: 'triclinic',
    zh: '三斜',
    lc: 'N',
    moduli: '—',
    phases: '—',
    note: '需在表中提供完整 c_ij',
  },
];

export function DigitalTwinHelpPanel() {
  return (
    <div className="dt-help-wrap" aria-label="使用说明与格式文档">
      <details className="dt-help" open>
        <summary>使用说明</summary>
        <div className="dt-help-body">
          <ol className="dt-help-list">
            <li>
              <strong>选择数据来源</strong>：顶部可选「默认 Si SAM」（温压插值）、金属预设 Cu/Al/Ni/Ti，或上传/激活自定义表。
            </li>
            <li>
              <strong>上传并激活</strong>：登录后拖入 <code>.dat</code> / <code>.xlsx</code>，或在侧栏选择已保存文件后点「使用所选文件」。当前生效配置会显示在文件面板下方。
            </li>
            <li>
              <strong>调节工况</strong>：左侧滑块控制温度 T（K）、压强 P（GPa）、成分行索引；仅当当前数据检测到对应列时滑块才可用。
            </li>
            <li>
              <strong>查看结果</strong>：侧栏显示 Hill 体/剪切/杨氏模量与晶系信息；右侧三窗口为 Young 模量 E、最大泊松比 ν<sub>max</sub>、纵波速度 v<sub>l</sub> 的 Fedorov 各向异性曲面。
            </li>
            <li>
              <strong>窗口操作</strong>：拖动标题栏移动、右下角缩放、最小化/关闭；已关闭或最小化窗口可在侧栏坞中恢复。
            </li>
            <li>
              <strong>刷新</strong>：改 T/P/成分后会自动刷新标量与曲面；也可点「手动刷新（标量+曲面）」。
            </li>
            <li>
              <strong>参数扫描</strong>：在「参数扫描动效」中选择扫描 T、P 或成分，可生成动态演示（需数据含对应维度）。
            </li>
          </ol>
          <p className="dt-help-note">
            侧栏 <strong>AVR</strong>、<strong>Zener A</strong>、<strong>cij_method</strong> 表示各向异性来源：单晶拟合、晶系近似或表内弹性常数。
          </p>
        </div>
      </details>

      <details className="dt-help">
        <summary>文件格式说明</summary>
        <div className="dt-help-body">
          <p>支持扩展名：<code>.dat</code>、<code>.txt</code>、<code>.csv</code>、<code>.xlsx</code>。系统自动识别以下三类之一：</p>

          <h4 className="dt-help-h4">① HTEM 温压网格（htem_grid）</h4>
          <p>必含列 <code>T(K)</code>、<code>P(GPa)</code>、<code>C11</code>、<code>C12</code>、<code>C44</code> 等；用于切换服务器 HTEM SAM 插值曲面。</p>

          <h4 className="dt-help-h4">② 成分 + 弹性常数表（alloy_table · cij）</h4>
          <p>
            必含 <code>Alloy</code> 或 <code>wt%</code> 成分列，以及 <code>c11</code>、<code>c12</code>、<code>c44</code>（六方等晶系需对应全部独立常数）。
            可选 <code>phases</code>、<code>crystal_system</code> / <code>LC</code> / <code>晶系</code>。
          </p>

          <h4 className="dt-help-h4">③ Hill 模量成分表（alloy_table · moduli_hill）</h4>
          <p>典型 Excel 表头（与 HTEM 输出习惯一致）：</p>
          <div className="dt-help-table-scroll">
            <table className="dt-help-table">
              <thead>
                <tr>
                  <th>类别</th>
                  <th>列名（任选识别）</th>
                  <th>用途</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>成分</td>
                  <td>
                    <code>wt%</code>、<code>at%</code>、<code>Alloys</code>、<code>phases</code>
                  </td>
                  <td>行标签与晶系推断</td>
                </tr>
                <tr>
                  <td>Voigt</td>
                  <td>
                    <code>BV</code>、<code>GV</code>、<code>Ev</code>、<code>nu_V</code>、<code>KV</code>、<code>HV</code>
                  </td>
                  <td>立方单晶反推（fcc/bcc 时）</td>
                </tr>
                <tr>
                  <td>Reuss</td>
                  <td>
                    <code>BR</code>、<code>GR</code>、<code>ER</code>、<code>nu_R</code>、<code>KR</code>、<code>HR</code>
                  </td>
                  <td>同上</td>
                </tr>
                <tr>
                  <td>Hill（侧栏优先）</td>
                  <td>
                    <code>BH</code>、<code>GH</code>、<code>EH</code>、<code>nu_H</code>、<code>KH</code>、<code>HH</code>
                  </td>
                  <td>侧栏 B/G/E/ν；各晶系 moduli 反推基准</td>
                </tr>
                <tr>
                  <td>各向异性指标</td>
                  <td>
                    <code>AVR</code>、<code>Au</code>
                  </td>
                  <td>多晶剪切各向异性等；单斜近似时使用 AVR</td>
                </tr>
                <tr>
                  <td>显式晶系</td>
                  <td>
                    <code>crystal_system</code>、<code>LC</code>、<code>晶系</code>
                  </td>
                  <td>覆盖 phases 自动推断，如 <code>monoclinic</code>、<code>M</code>、<code>单斜</code></td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="dt-help-note">
            模量列读取优先级：B/G/E/ν 优先 Hill 列（BH、GH、EH、nu_H），其次 Voigt/Reuss。仅 BH+GH、无 BV/BR/GV/GR 时，按晶系做 moduli 近似（见下表）。
          </p>
        </div>
      </details>

      <details className="dt-help">
        <summary>支持晶系与 phases 识别</summary>
        <div className="dt-help-body">
          <p>
            推断顺序：<strong>表内 crystal_system / LC 列</strong> → <strong>phases 关键词</strong> → 默认
            <code> isotropic</code>（多晶有效）。上传后可在侧栏查看 <code>crystal_display_zh</code>、<code>htem_lc</code>、
            <code>cij_method</code>。
          </p>
          <div className="dt-help-table-scroll">
            <table className="dt-help-table">
              <thead>
                <tr>
                  <th>晶系 id</th>
                  <th>中文</th>
                  <th>HTEM LC</th>
                  <th>moduli 反推</th>
                  <th>phases 示例</th>
                  <th>说明</th>
                </tr>
              </thead>
              <tbody>
                {CRYSTAL_SYSTEMS.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <code>{row.id}</code>
                    </td>
                    <td>{row.zh}</td>
                    <td>{row.lc}</td>
                    <td>{row.moduli}</td>
                    <td>{row.phases}</td>
                    <td>{row.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="dt-help-note">
            需要真实单晶各向异性曲面时，建议在表中直接提供该晶系的全部独立弹性常数（如单斜 13 个 C<sub>ij</sub>），或确保 phases / crystal_system 与数据物理意义一致。
          </p>
        </div>
      </details>
    </div>
  );
}
