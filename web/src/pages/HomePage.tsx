import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { pythonApi } from '../api/pythonApi';
import { RevealOnScroll } from '../components/RevealOnScroll';

function parseElementInput(raw: string): { element: string; num_element: number } | null {
  const match = raw.trim().match(/^(\d*)([A-Za-z-]+)$/);
  if (!match) return null;
  const numStr = match[1] || '1';
  const num_element = parseInt(numStr, 10);
  if (!Number.isFinite(num_element) || num_element < 1) return null;
  return { element: match[2], num_element };
}

function attachHomeStarfield(canvas: HTMLCanvasElement): () => void {
  const gctx = canvas.getContext('2d');
  if (!gctx) return () => {};
  const renderCtx = gctx;

  const numPoints = 80;
  const linkDistance = 130;
  type Pt = { x: number; y: number; vx: number; vy: number; radius: number; alpha: number };
  const points: Pt[] = [];

  function sizeCanvas() {
    const rect = canvas.getBoundingClientRect();
    const w = Math.max(1, Math.floor(rect.width));
    const h = Math.max(1, Math.floor(rect.height));
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }
  }

  function initPoints() {
    points.length = 0;
    for (let i = 0; i < numPoints; i++) {
      points.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        vx: (Math.random() - 0.5) * 1.2,
        vy: (Math.random() - 0.5) * 1.2,
        radius: 1.2 + Math.random() * 1.6,
        alpha: 0.35 + Math.random() * 0.45,
      });
    }
  }

  sizeCanvas();
  initPoints();

  let raf = 0;
  function update() {
    renderCtx.clearRect(0, 0, canvas.width, canvas.height);

    for (let i = 0; i < points.length; i++) {
      for (let j = i + 1; j < points.length; j++) {
        const dx = points[i].x - points[j].x;
        const dy = points[i].y - points[j].y;
        const dist = Math.hypot(dx, dy);
        if (dist < linkDistance) {
          const opacity = (1 - dist / linkDistance) * 0.22;
          renderCtx.strokeStyle = `rgba(6, 182, 212, ${opacity})`;
          renderCtx.lineWidth = 0.6;
          renderCtx.beginPath();
          renderCtx.moveTo(points[i].x, points[i].y);
          renderCtx.lineTo(points[j].x, points[j].y);
          renderCtx.stroke();
        }
      }
    }

    for (const point of points) {
      point.x += point.vx;
      point.y += point.vy;
      if (point.x <= 0 || point.x >= canvas.width) point.vx = -point.vx;
      if (point.y <= 0 || point.y >= canvas.height) point.vy = -point.vy;
      renderCtx.fillStyle = `rgba(6, 182, 212, ${point.alpha})`;
      renderCtx.beginPath();
      renderCtx.arc(point.x, point.y, point.radius, 0, Math.PI * 2);
      renderCtx.fill();
    }
    raf = requestAnimationFrame(update);
  }
  raf = requestAnimationFrame(update);

  const ro = new ResizeObserver(() => {
    sizeCanvas();
    initPoints();
  });
  ro.observe(canvas.parentElement ?? canvas);

  return () => {
    cancelAnimationFrame(raf);
    ro.disconnect();
  };
}

export function HomePage() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [demoOpen, setDemoOpen] = useState(false);
  const [inputThing, setInputThing] = useState('2U-Nb');
  const [resultText, setResultText] = useState('');
  const [homeQuery, setHomeQuery] = useState('Cu');
  const [homeStructure, setHomeStructure] = useState('all');
  const [homeSearchResult, setHomeSearchResult] = useState('');

  useEffect(() => {
    document.title = '金属弹性性质集成平台';
  }, []);

  useEffect(() => {
    const cvs = canvasRef.current;
    if (!cvs) return;
    return attachHomeStarfield(cvs);
  }, []);

  const submitMaterial = useCallback(async () => {
    if (!inputThing.trim()) {
      window.alert('请输入元素信息！');
      return;
    }
    const parsed = parseElementInput(inputThing);
    if (!parsed) {
      window.alert("输入格式不正确，请使用类似 '2U-Nb' 的格式");
      return;
    }
    setResultText('正在更改元素...');
    try {
      const submitRes = await pythonApi.submitElement({
        element: parsed.element,
        num_element: parsed.num_element,
      });
      if (submitRes.status !== 'success') {
        throw new Error('服务器未返回成功状态');
      }
      setResultText('元素已更改，等待服务器处理...');
      await new Promise<void>((resolve) => {
        setTimeout(resolve, 3000);
      });
      const data = await pythonApi.queryData(parsed.element, parsed.num_element);
      setResultText(data.message.join('\n'));
    } catch (error) {
      setResultText(`操作失败: ${(error as Error).message}`);
    }
  }, [inputThing]);

  const refreshResult = useCallback(async () => {
    if (!inputThing.trim()) {
      setResultText('请先输入元素信息');
      return;
    }
    const parsed = parseElementInput(inputThing);
    if (!parsed) {
      setResultText("输入格式不正确，请使用类似 '2U-Nb' 的格式");
      return;
    }
    setResultText('正在获取数据，请稍候...');
    try {
      const data = await pythonApi.queryData(parsed.element, parsed.num_element);
      setResultText(data.message.join('\n'));
    } catch (error) {
      setResultText(`获取数据失败: ${(error as Error).message}`);
    }
  }, [inputThing]);

  const runHomeParallelSearch = useCallback(async () => {
    const q = homeQuery.trim();
    if (!q) {
      setHomeSearchResult('请输入元素或化学式');
      return;
    }
    setHomeSearchResult('正在并联检索本地 MySQL 与 MP-API…');
    try {
      const res = (await pythonApi.homeSearch({
        q,
        filters: { structure: homeStructure },
      })) as {
        local?: { elements?: unknown[]; materials?: unknown[]; mp_source?: string };
        mp_api?: { message?: string[]; error?: string };
        merged_count?: number;
      };
      const localCount =
        (res.local?.elements?.length ?? 0) + (res.local?.materials?.length ?? 0);
      const mpLines = res.mp_api?.message?.slice(0, 8) ?? [];
      setHomeSearchResult(
        [
          `本地命中 ${localCount} 条（MP 源: ${res.local?.mp_source ?? 'n/a'}）`,
          `MP-API 摘要 ${mpLines.length} 行`,
          ...mpLines.map(String),
          res.mp_api?.error ? `MP 错误: ${res.mp_api.error}` : '',
        ]
          .filter(Boolean)
          .join('\n'),
      );
    } catch (error) {
      setHomeSearchResult(`检索失败: ${(error as Error).message}`);
    }
  }, [homeQuery, homeStructure]);

  return (
    <div className="home-mainpage">
      <div className="home-hero-wrap motion-hero-bg">
        <canvas ref={canvasRef} className="home-background-canvas" aria-hidden />
        <div className="home-hero-inner">
          <div className="home-main-box">
            <div className="home-essential-box motion-fade-up motion-card-lift">
              <div className="home-project-content">
                <h1 className="home-project-title motion-title-shimmer">金属弹性性质集成平台</h1>
                <p className="home-project-subtitle">
                  An Integrated Platform of Elastic Properties for Metals
                </p>
                <h2>项目简介</h2>
                <p>
                  金属弹性常数是连接晶体微观结构与宏观力学响应的核心物理量。针对当前弹性性质计算方法不统一、计算结果分散、跨来源对比困难、分析流程难以闭环等问题，本课题围绕金属单质弹性常数的第一性原理计算与 Web 集成平台开展研究。
                </p>
                <p>
                  计算方面，采用 VASP 在 DFT-PAW-PBE 框架下对 Li、Na、Sc、Ti、V、Ni、Cu、Zn、Mo、Rh 等 20 余种纯金属开展弹性常数计算，并行采用应力-应变法与能量-应变法，经 Voigt-Reuss-Hill 平均得到多晶模量，并以 Born 稳定性判据进行力学稳定性检验。
                </p>
                <p>
                  平台方面，采用 Python + TypeScript/React + Rust（Actix-web）三层架构，以 MySQL 统一存储弹性数据与计算元数据，实现多源检索、三维晶体结构可视化、曲线拟合与 HTEM 半解析建模分析，支持 VASP 单元素数据入库审核、浏览器内远程终端及温压-成分空间各向异性曲面实时渲染。
                </p>
                <h2>选题背景</h2>
                <p>
                  VASP、Quantum ESPRESSO 等程序已产出大量弹性数据，Materials Project、AFLOW 等开放数据库亦提供了检索与 API 服务。然而课题组内部常见的工作方式仍是：计算结果分散存放于各次任务文件夹，文献数据靠手工摘录，趋势对比与可视化在 Excel 或脚本中离线完成——数据量增大后，检索效率、版本追溯与跨来源对比均成为瓶颈。
                </p>
                <p>
                  本平台的定位是工程载体：以金属弹性为第一性物理对象，在入库前施加 Born/Mouhat 稳定性约束与双方法交叉校验，实现「VASP/HTEM 计算 → 数据治理 → 交互分析」闭环，为金属弹性数据的专题化汇聚、物理一致性约束与交互式分析提供可检索、可展示、可交互的使用环境。
                </p>
                <h2>平台核心模块</h2>
                <ul className="home-module-list">
                  <li>
                    <strong>多源检索</strong>：本地 MySQL 物性库与 Materials Project 并联查询，支持晶系、计算方法与稳定性筛选
                  </li>
                  <li>
                    <strong>可视化分析</strong>：元素周期表交互检索、弹性矩阵展示、Three.js 晶体结构渲染、SSH 远程终端
                  </li>
                  <li>
                    <strong>数据治理</strong>：VASP 输出自动解析、Born/Mouhat 检验、MARE 标注与管理员四步 QC 审批入库
                  </li>
                  <li>
                    <strong>数字孪生</strong>：HTEM SAM 半解析外推，实时渲染杨氏模量 E、最大泊松比与纵波声速各向异性曲面（可调 T、P）
                  </li>
                  <li>
                    <strong>数据拟合</strong>：多项式/指数/对数/正弦曲线拟合，结果可关联至化合物记录
                  </li>
                </ul>
              </div>
            </div>
            <div className="home-sec-box motion-fade-up motion-delay-2 motion-card-lift">
              <div
                className="home-sec-box-header"
                onClick={() => setDemoOpen((o) => !o)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setDemoOpen((o) => !o);
                  }
                }}
              >
                <span className="home-sec-box-title">示例制作脚本-material project api 获取元素性质</span>
                <button
                  type="button"
                  className={`home-toggle-button${demoOpen ? ' active' : ''}`}
                  aria-label={demoOpen ? '收起' : '展开'}
                >
                  ▼
                </button>
              </div>
              <div className={`home-sec-box-content${demoOpen ? ' active' : ''}`}>
                <div className="home-input-container">
                  <input
                    id="home_input_thing"
                    type="text"
                    placeholder="实例(请区分好大小写)：2U-Nb"
                    value={inputThing}
                    onChange={(e) => setInputThing(e.target.value)}
                  />
                  <button type="button" onClick={submitMaterial}>
                    更改元素
                  </button>
                </div>
                <div className="home-result-container">
                  <textarea id="home_result_of_search" className="home-result-textarea" readOnly value={resultText} />
                  <button type="button" className="home-refrash-button" onClick={refreshResult}>
                    确认刷新
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <RevealOnScroll>
        <section className="home-site-section">
          <div className="home-container">
            <h2 className="home-section-title">多源弹性数据检索</h2>
          <p>并联查询本地 MySQL 物性库与 Materials Project；可按晶系筛选（fcc/bcc/hcp）。</p>
          <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
            <label className="field">
              元素/化学式
              <input value={homeQuery} onChange={(e) => setHomeQuery(e.target.value)} placeholder="Cu / Al / Nb" />
            </label>
            <label className="field">
              晶系
              <select value={homeStructure} onChange={(e) => setHomeStructure(e.target.value)}>
                <option value="all">全部</option>
                <option value="fcc">fcc</option>
                <option value="bcc">bcc</option>
                <option value="hcp">hcp</option>
              </select>
            </label>
            <button type="button" className="btn" onClick={runHomeParallelSearch}>
              并联检索
            </button>
          </div>
          <textarea className="home-result-textarea" readOnly rows={8} value={homeSearchResult} />
        </div>
      </section>
      </RevealOnScroll>

      <RevealOnScroll delayMs={80}>
        <section id="vasp-documentation" className="home-site-section home-vasp-documentation">
          <div className="home-container">
            <h2 className="home-section-title">VASP计算元素力学性质辅助文档</h2>
          <div className="home-doc-content">
            <h3>计算流程概述</h3>
            <div className="home-flow-chart">
              <div className="home-text-flow-chart">
                <div className="home-flow-step">输入信息生成文件</div>
                <div className="home-flow-arrow">↓</div>
                <div className="home-flow-step">初始弛豫</div>
                <div className="home-flow-arrow">↓</div>
                <div className="home-flow-step">生成应变结构</div>
                <div className="home-flow-arrow">↓</div>
                <div className="home-flow-step">应变结构弛豫计算</div>
                <div className="home-flow-arrow">↓</div>
                <div className="home-flow-step">应变结构静态计算</div>
                <div className="home-flow-arrow">↓</div>
                <div className="home-flow-step">结果分析</div>
              </div>
            </div>
            <h3>基本文件说明</h3>
            <h4>VASP四个基本输入文件</h4>
            <ul className="home-file-list">
              <li>
                <strong>POTCAR</strong>: 赝势文件，由VASP官方提供
                <ul>
                  <li>用势函数表示内层电子，减小计算量</li>
                  <li>不同元素有多种赝势可选</li>
                </ul>
              </li>
              <li>
                <strong>POSCAR</strong>: 结构文件
                <ul>
                  <li>包含晶格常数</li>
                  <li>原子在晶胞内的精确位置坐标</li>
                  <li>支持分数坐标和笛卡尔坐标系</li>
                </ul>
              </li>
              <li>
                <strong>INCAR</strong>: 计算控制文件
                <ul>
                  <li>定义计算方式</li>
                  <li>设置计算精度</li>
                  <li>控制计算参数</li>
                </ul>
              </li>
              <li>
                <strong>KPOINTS</strong>: K点设置文件
                <ul>
                  <li>包含倒易空间点网格的坐标和权重</li>
                  <li>K点数量影响计算精度和计算量</li>
                  <li>可选择只计算Gamma点（布里渊区中心）</li>
                </ul>
              </li>
            </ul>
            <h4>主要输出文件</h4>
            <ul className="home-file-list">
              <li>
                <strong>OUTCAR</strong>: 包含计算的详细信息和结果
              </li>
              <li>
                <strong>CONTCAR</strong>: 计算后的结构信息，可用于后续计算
              </li>
            </ul>
            <h3>程序组成</h3>
            <ul className="home-program-list">
              <li>
                <strong>anisotropy.py</strong>: 各向异性计算和可视化
              </li>
              <li>
                <strong>auto_run.py</strong>: 自动化生成输入文件和管理计算任务
              </li>
              <li>
                <strong>elasticity.py</strong>: 计算弹性常数和力学性质
              </li>
              <li>
                <strong>HTEM.py</strong>: 主程序入口，协调各模块运行
              </li>
              <li>
                <strong>lib_HTEM.py</strong>: 提供辅助函数和工具
              </li>
              <li>
                <strong>method_npt.py</strong>: 处理NPT模拟数据，计算弹性常数
              </li>
              <li>
                <strong>parameter.py</strong>: 定义和处理输入参数
              </li>
              <li>
                <strong>job_sbatch_1.sh和job_sbatch_2.sh</strong>: 提交计算任务脚本
              </li>
            </ul>
            <h3>计算步骤详解</h3>
            <div className="home-calculation-steps">
              <div className="home-step">
                <h4>1. 输入信息生成文件</h4>
                <ul>
                  <li>输入元素名称、晶体结构、晶格常数</li>
                  <li>设置k点密度控制计算精度</li>
                  <li>生成VASP所需的四个基本文件</li>
                </ul>
              </div>
              <div className="home-step">
                <h4>2. 初始弛豫计算</h4>
                <ul>
                  <li>使系统能量达到最低状态</li>
                  <li>优化晶体结构，消除结构不合理之处</li>
                  <li>避免非物理效应，提高后续计算准确性</li>
                </ul>
              </div>
              <div className="home-step">
                <h4>3. 生成应变结构</h4>
                <ul>
                  <li>对晶胞施加应变</li>
                  <li>生成新的晶格结构用于后续计算</li>
                </ul>
              </div>
              <div className="home-step">
                <h4>4. 应变结构弛豫计算</h4>
                <ul>
                  <li>保证应变后的结构处于能量最低状态</li>
                  <li>确保结构稳定性</li>
                </ul>
              </div>
              <div className="home-step">
                <h4>5. 应变结构静态计算</h4>
                <ul>
                  <li>进行电子结构计算</li>
                  <li>获取系统总能量和应力</li>
                  <li>通过多项式拟合得到能量-应变关系曲线</li>
                </ul>
              </div>
              <div className="home-step">
                <h4>6. 结果分析</h4>
                <ul>
                  <li>提取弹性常数</li>
                  <li>计算力学性质（弹性模量、泊松比等）</li>
                  <li>应力-应变方法与能量-应变方法结果对比验证</li>
                </ul>
              </div>
            </div>
            <h3>研究内容重点</h3>
            <div className="home-research-focus">
              <div className="home-focus-item">
                <h4>晶系分类</h4>
                <ul>
                  <li>立方晶系：FCC（铝、铜、金）、BCC（铁、铬、钒）</li>
                  <li>六方晶系：HCP（镁、锌）</li>
                </ul>
              </div>
              <div className="home-focus-item">
                <h4>计算方法对比</h4>
                <ul>
                  <li>应力-应变法：±0.01 小应变，线性拟合应力张量，收敛敏感但实现直接</li>
                  <li>能量-应变法：−0.02～+0.02 五点拟合能量二次项，与应力法交叉校验</li>
                  <li>双方法一致性良好者入库；偏差超限或违反 Born 判据者自动退回</li>
                </ul>
              </div>
              <div className="home-focus-item">
                <h4>弹性各向异性数字孪生</h4>
                <p className="home-focus-note">
                  基于 HTEM SAM 的 Young 模量、最大泊松比与纵波声速随方向的三维曲面，可调工况 T、P。
                </p>
                <p className="home-focus-cta-wrap">
                  <Link to="/digital-twin" className="home-focus-cta">
                    进入孪生可视化 →
                  </Link>
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>
      </RevealOnScroll>

      <RevealOnScroll delayMs={120}>
      <section id="documentation" className="home-site-section home-documentation">
        <div className="home-container">
          <h2 className="home-section-title">辅助文档</h2>
          <div className="home-doc-content home-doc-content--user">
            <h3>使用方法</h3>
            <p>
              注册登录后，进入「可视化网页」拖动周期表元素检索本地库与 MP，查看弹性矩阵与 3D 晶格；「数据录入」或终端提交 VASP 结果待审；「数据拟合」完成趋势外推并关联化合物；「弹性孪生可视化」体验 HTEM 各向异性曲面。
            </p>
            <h4>可视化网页（主要功能）</h4>
            <div className="home-image-placeholder">
              <img src="/img/doc/visual.jpg" alt="可视化界面" className="home-doc-image" />
            </div>
            <p>如图所示，元素周期表中的元素可拖动。拖动到右侧窗口时会进行一时的加载。加载完毕后可选择材料。</p>
            <p>当本地数据库中没有此材料数据时仅会访问mp-api的数据库。如图所示，选择材料中并没有db-data的选项。</p>
            <div className="home-image-placeholder">
              <img src="/img/doc/no-db-data.jpg" alt="无本地数据" className="home-doc-image" />
            </div>
            <p>
              如果数据库中有材料数据，则会有db-data的选项出现，选择后下方数据框中会显示数据库当中的数据，下方还有着此材料数据的结构图可供查看。并且元素周期表下方有着弹性常数矩阵，可供使用者观看。
            </p>
            <div className="home-image-placeholder">
              <img src="/img/doc/with-db-data.jpg" alt="有本地数据" className="home-doc-image" />
            </div>
            <p>在第二页「数据录入」或可视化页终端可提交 VASP 入库；管理员在「我的 → 管理审核」完成四步 QC 最后确认。</p>
            <p>在可视化网页的最后一页是服务器终端，可供临时使用。</p>
            <div className="home-image-placeholder">
              <img src="/img/doc/terminal.jpg" alt="服务器终端" className="home-doc-image" />
            </div>
            <p>通过实际操作演示，验证了平台的可用性和实用性。用户可以方便地通过平台获取所需的材料数据和计算结果。</p>
          </div>
        </div>
      </section>
      </RevealOnScroll>
    </div>
  );
}
