/* Gráficos de Mi Gestión con Chart.js (cargado en mi_gestion.html).
   Los datos vienen de la vista en un <script type="application/json" id="datos-graficos"> (json_script de
   Django, que escapa el contenido): aquí solo se dibujan, no se calcula nada.
   - #grafico-avance: medidor semicircular del avance contra lo esperado a hoy (marca negra).
   - #grafico-estados: anillo con las actividades por estado.
   - #grafico-barras: barras horizontales con una línea de referencia (meta). */
(function () {
    var fuente = document.getElementById('datos-graficos');
    if (!fuente || !window.Chart) { return; }
    var datos = JSON.parse(fuente.textContent);

    var COLOR = { VERDE: '#2E9E5B', AMBAR: '#F2A900', ROJO: '#C41230', '': '#9A9090' };
    var GRIS = '#EEE9E7';
    var movimiento = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    Chart.defaults.font.family = '"Segoe UI", system-ui, -apple-system, sans-serif';
    Chart.defaults.color = '#6b6262';
    if (!movimiento) { Chart.defaults.animation = false; }

    function numero(valor) { return valor.toLocaleString('es-CL', { maximumFractionDigits: 1 }); }

    // 1. Medidor de avance (media dona). La escala llega al 100% o al avance, si lo supera (tope 120%)
    var lienzo = document.getElementById('grafico-avance');
    if (lienzo && datos.avance) {
        var a = datos.avance;
        var maximo = Math.max(100, a.valor, a.objetivo);
        var marcaObjetivo = {
            id: 'marcaObjetivo',
            afterDatasetsDraw: function (grafico) {
                var arco = grafico.getDatasetMeta(0).data[0];
                if (!arco) { return; }
                var angulo = Math.PI + Math.PI * (a.objetivo / maximo);
                var ctx = grafico.ctx;
                ctx.save();
                ctx.strokeStyle = '#1F1A1A';
                ctx.lineWidth = 3;
                ctx.beginPath();
                ctx.moveTo(arco.x + Math.cos(angulo) * (arco.innerRadius - 4), arco.y + Math.sin(angulo) * (arco.innerRadius - 4));
                ctx.lineTo(arco.x + Math.cos(angulo) * (arco.outerRadius + 4), arco.y + Math.sin(angulo) * (arco.outerRadius + 4));
                ctx.stroke();
                ctx.restore();
            }
        };
        new Chart(lienzo, {
            type: 'doughnut',
            data: { datasets: [{
                data: [Math.min(a.valor, maximo), Math.max(maximo - a.valor, 0)],
                backgroundColor: [COLOR[a.color] || COLOR[''], GRIS],
                borderWidth: 0, borderRadius: 6
            }] },
            options: {
                rotation: -90, circumference: 180, cutout: '74%', aspectRatio: 1.7,
                plugins: { legend: { display: false }, tooltip: { enabled: false } }
            },
            plugins: [marcaObjetivo]
        });
    }

    // 2. Actividades por estado (anillo con leyenda a la derecha)
    lienzo = document.getElementById('grafico-estados');
    if (lienzo && datos.total_estados) {
        new Chart(lienzo, {
            type: 'doughnut',
            data: {
                labels: datos.estados.map(function (e) { return e.etiqueta; }),
                datasets: [{
                    data: datos.estados.map(function (e) { return e.valor; }),
                    backgroundColor: datos.estados.map(function (e) { return e.color; }),
                    borderColor: '#ffffff', borderWidth: 3, hoverOffset: 6
                }]
            },
            options: {
                cutout: '68%', maintainAspectRatio: false,
                plugins: { legend: { position: 'right', labels: { usePointStyle: true, pointStyle: 'circle', boxWidth: 8, padding: 14 } } }
            }
        });
    }

    // 3. Barras horizontales con línea de referencia
    lienzo = document.getElementById('grafico-barras');
    if (lienzo && datos.barras && datos.barras.filas.length) {
        var b = datos.barras;
        var lineaReferencia = {
            id: 'lineaReferencia',
            afterDatasetsDraw: function (grafico) {
                var x = grafico.scales.x.getPixelForValue(b.referencia);
                var area = grafico.chartArea;
                var ctx = grafico.ctx;
                ctx.save();
                ctx.strokeStyle = '#1F1A1A';
                ctx.setLineDash([5, 4]);
                ctx.lineWidth = 1.5;
                ctx.beginPath();
                ctx.moveTo(x, area.top);
                ctx.lineTo(x, area.bottom);
                ctx.stroke();
                ctx.setLineDash([]);
                ctx.fillStyle = '#1F1A1A';
                ctx.font = '600 11px "Segoe UI", sans-serif';
                var texto = b.texto_referencia + ': ' + numero(b.referencia) + '%';
                var ancho = ctx.measureText(texto).width;
                ctx.textAlign = 'left';  // centrado sobre la línea, sin salirse del gráfico
                ctx.fillText(texto, Math.min(Math.max(x - ancho / 2, area.left), area.right - ancho), area.top - 6);
                ctx.restore();
            }
        };
        lienzo.parentElement.style.height = Math.max(160, b.filas.length * 42 + 50) + 'px';
        var maximoBarras = Math.max(100, b.referencia, Math.max.apply(null, b.filas.map(function (f) { return f.valor; })));
        new Chart(lienzo, {
            type: 'bar',
            data: {
                labels: b.filas.map(function (f) { return f.etiqueta; }),
                datasets: [{
                    data: b.filas.map(function (f) { return f.valor; }),
                    backgroundColor: b.filas.map(function (f) { return f.valor >= b.referencia ? '#2E9E5B' : '#C41230'; }),
                    borderRadius: 6, barThickness: 18
                }]
            },
            options: {
                indexAxis: 'y', maintainAspectRatio: false,
                layout: { padding: { top: 22, right: 12 } },
                scales: {
                    x: { min: 0, suggestedMax: Math.ceil(maximoBarras / 10) * 10, grid: { color: '#F1ECEA' },
                         ticks: { callback: function (v) { return v + '%'; } } },
                    y: { grid: { display: false } }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: function (c) { return ' ' + numero(c.parsed.x) + '%'; } } }
                }
            },
            plugins: [lineaReferencia]
        });
    }
})();
