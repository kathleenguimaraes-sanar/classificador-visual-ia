'use strict';

// ==========================================================
// ESTADO DA APLICAÇÃO
// ==========================================================

const state = {
    connected: false,
    jobsTimer: null,
    jwPropertyId: '',
    jwLibrary: '',
    analyzingSingle: false
};

// ==========================================================
// SELEÇÃO DE ELEMENTOS
// ==========================================================

const $ = (selector) => document.querySelector(selector);

const $$ = (selector) => document.querySelectorAll(selector);

// ==========================================================
// BIBLIOTECAS JW PLAYER
// ==========================================================

const jwLibraries = {
    DEV: {
        name: 'DEV',
        propertyId: 'FvJr6FNj',
        url: 'https://dashboard.jwplayer.com/p/FvJr6FNj/media'
    },

    EBSERH: {
        name: 'EBSERH',
        propertyId: 'UBP82vRQ',
        url: 'https://dashboard.jwplayer.com/p/UBP82vRQ/media'
    },

    SANARFLIX: {
        name: 'SANARFLIX',
        propertyId: 'XK8A5jD7',
        url: 'https://dashboard.jwplayer.com/p/XK8A5jD7/media'
    },

    VIDEOSSANAR: {
        name: 'VIDEOS SANAR',
        propertyId: 'XdfUPSCL',
        url: 'https://dashboard.jwplayer.com/p/XdfUPSCL/media'
    }
};

// ==========================================================
// ESPECIFICAÇÃO DOS MODELOS DE AULA
// ==========================================================

const MODEL_SPECIFICATIONS = {
    'Teórica core':
        'Modelo/classificação utilizada para identificar ' +
        'aulas predominantemente teóricas.',

    'Teórica apenas slide':
        'Aula teórica assíncrona, gravada com áudio do ' +
        'professor e a tela do slide.',

    Demonstrativo:
        'Aula prática, demonstração de exame em paciente, ' +
        'professor mostrando o exame.',

    'Teórica core + demonstrativo':
        'Aula que alterna entre aula teórica core e ' +
        'demonstrativo.'
};

// Índice normalizado (sem espaços nas pontas, minúsculo) para
// que pequenas diferenças de formatação/capitalização vindas da
// API não impeçam a identificação da especificação.
const MODEL_SPECIFICATIONS_BY_KEY = Object.fromEntries(
    Object.entries(MODEL_SPECIFICATIONS).map(
        ([name, specification]) => [
            name.trim().toLowerCase(),
            specification
        ]
    )
);

// ==========================================================
// CONFIGURAÇÃO DOS PROVEDORES DE IA
// ==========================================================

const providerDefaults = {
    Claude: 'claude-sonnet-4-5',
    Gemini: 'gemini-flash-latest',
    Ollama: 'llava:7b'
};

// ==========================================================
// BIBLIOTECA PADRÃO
// ==========================================================

const DEFAULT_JW_LIBRARY = 'SANARFLIX';

// ==========================================================
// API
// ==========================================================

async function api(url, options = {}) {
    const response = await fetch(url, options);

    let body = {};

    try {
        body = await response.json();
    } catch {
        body = {};
    }

    if (!response.ok) {
        throw new Error(
            body.detail ||
            body.message ||
            `Erro ${response.status}`
        );
    }

    return body;
}

// ==========================================================
// STATUS DOS SERVIÇOS (GEMINI / CLAUDE / OLLAMA / JW AGENT)
// ==========================================================
//
// Ollama só faz parte do ambiente local (ENABLE_OLLAMA=false
// em produção). Em vez de reescrever o formulário, apenas
// oculta a opção quando o backend informa que ela não está
// disponível — o restante da interface não muda.

async function applyServiceStatus() {
    try {
        const status =
            await api('/api/status');

        if (status.ollama_enabled === false) {
            const providerSelect =
                $('#provider');

            const ollamaOption =
                providerSelect?.querySelector(
                    'option[value="Ollama"]'
                );

            if (ollamaOption) {
                ollamaOption.remove();
            }
        }
    } catch (error) {
        console.error(
            'Erro ao carregar status dos serviços:',
            error
        );
    }
}

// ==========================================================
// TOAST
// ==========================================================

function toast(message) {
    const element = $('#toast');

    if (!element) {
        return;
    }

    element.textContent = String(message || '');

    element.classList.add('show');

    setTimeout(() => {
        element.classList.remove('show');
    }, 4000);
}

// ==========================================================
// ESCAPE HTML
// ==========================================================

function escapeHtml(value) {
    return String(value ?? '').replace(
        /[&<>'"]/g,
        (character) => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            "'": '&#39;',
            '"': '&quot;'
        })[character]
    );
}

// ==========================================================
// EXTRAIR PROPERTY ID DA URL
// ==========================================================

function extractPropertyIdFromUrl(url) {
    const value = String(url || '').trim();

    if (!value) {
        return '';
    }

    const match = value.match(
        /dashboard\.jwplayer\.com\/p\/([^/?#]+)/i
    );

    return match
        ? String(match[1]).trim()
        : '';
}

// ==========================================================
// ENCONTRAR BIBLIOTECA PELO PROPERTY ID
// ==========================================================

function getJWLibraryByPropertyId(propertyId) {
    const value = String(propertyId || '')
        .trim()
        .toUpperCase();

    if (!value) {
        return null;
    }

    for (const library of Object.values(jwLibraries)) {
        if (
            String(library.propertyId).toUpperCase() === value
        ) {
            return library;
        }
    }

    return null;
}

// ==========================================================
// ENCONTRAR BIBLIOTECA PELO VALOR DO SELECT
// ==========================================================

function resolveJWLibraryValue(value) {
    const normalized = String(value || '')
        .trim()
        .toUpperCase();

    if (!normalized) {
        return null;
    }

    if (jwLibraries[normalized]) {
        return {
            key: normalized,
            library: jwLibraries[normalized]
        };
    }

    const byProperty = getJWLibraryByPropertyId(normalized);

    if (byProperty) {
        const entry = Object.entries(jwLibraries).find(
            ([, library]) =>
                library.propertyId.toUpperCase() === normalized
        );

        if (entry) {
            return {
                key: entry[0],
                library: entry[1]
            };
        }
    }

    return null;
}

// ==========================================================
// OBTER SELECT DA BIBLIOTECA
// ==========================================================

function getJWLibrarySelector() {
    return (
        $('#jw-library') ||
        $('#jw-property') ||
        $('#jw-library-select')
    );
}

// ==========================================================
// OBTER BIBLIOTECA SELECIONADA
// ==========================================================

function getSelectedJWLibrary() {
    const selector = getJWLibrarySelector();

    if (!selector) {
        return null;
    }

    const resolved = resolveJWLibraryValue(selector.value);

    if (resolved) {
        return resolved.library;
    }

    const selectedOption =
        selector.options?.[selector.selectedIndex];

    if (selectedOption) {
        const text = String(
            selectedOption.textContent || ''
        )
            .trim()
            .toUpperCase();

        const byText = Object.entries(jwLibraries).find(
            ([, library]) =>
                library.name.trim().toUpperCase() === text
        );

        if (byText) {
            return byText[1];
        }
    }

    return null;
}

// ==========================================================
// OBTER CHAVE DA BIBLIOTECA
// ==========================================================

function getSelectedJWLibraryKey() {
    const selector = getJWLibrarySelector();

    if (!selector) {
        return '';
    }

    const resolved = resolveJWLibraryValue(selector.value);

    if (resolved) {
        return resolved.key;
    }

    const selectedLibrary = getSelectedJWLibrary();

    if (!selectedLibrary) {
        return '';
    }

    const entry = Object.entries(jwLibraries).find(
        ([, library]) => library === selectedLibrary
    );

    return entry ? entry[0] : '';
}

// ==========================================================
// ATUALIZAR LINK DO JW PLAYER
// ==========================================================

function updateJWLibraryLink() {
    const library = getSelectedJWLibrary();

    const link =
        $('#library-url') ||
        $('.library-url');

    if (!link) {
        return;
    }

    if (!library) {
        link.textContent =
            'Selecione uma biblioteca JW Player';

        link.removeAttribute('href');

        return;
    }

    const url =
        `https://dashboard.jwplayer.com/p/${library.propertyId}/media`;

    link.textContent = url.replace(
        'https://',
        ''
    );

    link.href = url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
}

// ==========================================================
// INICIALIZAR BIBLIOTECAS
// ==========================================================

function initializeJWProperties() {
    const selector = getJWLibrarySelector();

    if (!selector) {
        return;
    }

    if (!selector.options.length) {
        Object.entries(jwLibraries).forEach(
            ([key, library]) => {
                const option =
                    document.createElement('option');

                option.value = key;
                option.textContent = library.name;

                selector.appendChild(option);
            }
        );
    }

    let current = resolveJWLibraryValue(
        selector.value
    );

    if (!current) {
        const selectedOption =
            selector.options?.[selector.selectedIndex];

        if (selectedOption) {
            const text = String(
                selectedOption.textContent || ''
            )
                .trim()
                .toUpperCase();

            const entry = Object.entries(jwLibraries).find(
                ([, library]) =>
                    library.name.trim().toUpperCase() === text
            );

            if (entry) {
                current = {
                    key: entry[0],
                    library: entry[1]
                };
            }
        }
    }

    if (!current) {
        selector.value = DEFAULT_JW_LIBRARY;

        current = resolveJWLibraryValue(
            DEFAULT_JW_LIBRARY
        );
    }

    if (current) {
        selector.value = current.key;

        state.jwLibrary = current.key;
        state.jwPropertyId = current.library.propertyId;
    }

    updateJWLibraryLink();
}

// ==========================================================
// ATUALIZAR BOTÃO DE ANÁLISE INDIVIDUAL
// ==========================================================

const JWPLAYER_ID_PATTERN = /^[A-Za-z0-9]{8}$/;

function isValidJWPlayerId(value) {
    return JWPLAYER_ID_PATTERN.test(
        String(value || '').trim()
    );
}

function updateAnalysisButtons() {
    const singleButton =
        $('#analyze-single-id');

    if (singleButton) {
        const input =
            $('#single-jwplayer-id');

        const hasValidJWPlayerId =
            isValidJWPlayerId(input?.value);

        singleButton.disabled = !(
            state.connected &&
            hasValidJWPlayerId &&
            !state.analyzingSingle
        );
    }

    const uploadButton =
        $('#upload');

    if (uploadButton) {
        const fileInput =
            $('#spreadsheet');

        const hasFile = Boolean(
            fileInput?.files?.length
        );

        uploadButton.disabled = !(
            state.connected &&
            hasFile
        );
    }
}

// ==========================================================
// ALTERAÇÃO DA BIBLIOTECA
// ==========================================================

function registerJWLibraryChange() {
    const selector = getJWLibrarySelector();

    if (!selector) {
        return;
    }

    selector.addEventListener(
        'change',
        async () => {
            const library = getSelectedJWLibrary();

            const libraryKey =
                getSelectedJWLibraryKey();

            if (!library || !libraryKey) {
                state.jwLibrary = '';
                state.jwPropertyId = '';
                state.connected = false;

                applyConnection({
                    state: 'disconnected',
                    message:
                        'Selecione uma biblioteca JW Player.'
                });

                return;
            }

            state.jwLibrary = libraryKey;
            state.jwPropertyId = library.propertyId;
            state.connected = false;

            updateJWLibraryLink();

            applyConnection({
                state: 'disconnected',
                property_id: library.propertyId,
                library: libraryKey,
                message:
                    `Biblioteca ${library.name} selecionada.`
            });

            updateAnalysisButtons();

            const importResult =
                $('#import-result');

            if (importResult) {
                importResult.innerHTML = '';
            }

            const singleResult =
                $('#single-id-result');

            if (singleResult) {
                singleResult.innerHTML = '';
            }

            toast(
                `Biblioteca ${library.name} selecionada.`
            );

            // Reaproveita a sessão JW Player já conectada,
            // apenas trocando o contexto/property da pesquisa
            // — não solicita e-mail/senha novamente.
            await switchJWLibrary(
                library,
                libraryKey
            );
        }
    );
}

// ==========================================================
// NAVEGAÇÃO
// ==========================================================

function show(view) {
    $$('.view, .nav').forEach((element) => {
        element.classList.remove('active');
    });

    const targetView =
        $(`#view-${view}`);

    const targetNav =
        $(`.nav[data-view="${view}"]`);

    if (targetView) {
        targetView.classList.add('active');
    }

    if (targetNav) {
        targetNav.classList.add('active');
    }
}

$$('.nav').forEach((button) => {
    button.addEventListener(
        'click',
        () => {
            const targetView =
                button.dataset.view;

            if (
                targetView !== 'connection' &&
                !state.connected
            ) {
                toast(
                    'Conecte-se ao JW Player na Etapa 1 antes de continuar.'
                );

                show('connection');

                return;
            }

            show(targetView);
        }
    );
});

// ==========================================================
// ESTATÍSTICAS
// ==========================================================

// Os cards representam a EXECUÇÃO ATUAL, não o histórico
// completo do banco. /api/stats é global (todas as execuções
// já feitas), por isso não é usado aqui — em vez disso, busca
// /api/videos sem filtros (o mesmo endpoint que já é filtrado
// pelo backend por run_id) e calcula os números a partir dele.
// Sem filtro de busca/status/modelo: os cards sempre refletem
// a execução inteira, independente do que a tabela abaixo
// estiver mostrando.

async function loadStats() {
    try {
        const data =
            await api('/api/videos');

        const items =
            Array.isArray(data.items)
                ? data.items
                : [];

        const records = items.length;

        const media = new Set(
            items.map(
                (video) => video.jwplayer_id
            )
        ).size;

        const analyzed = new Set(
            items
                .filter(
                    (video) =>
                        video.status === 'Concluído'
                )
                .map(
                    (video) => video.jwplayer_id
                )
        ).size;

        const validated = new Set(
            items
                .filter(
                    (video) =>
                        video.validation_status ===
                        'Validado'
                )
                .map(
                    (video) => video.jwplayer_id
                )
        ).size;

        const progress =
            media > 0
                ? Math.min(
                    100,
                    Math.round(
                        (analyzed / media) * 100
                    )
                )
                : 0;

        const values = [
            ['Registros', records],
            ['Vídeos únicos', media],
            ['Analisados', analyzed],
            ['Validados', validated],
            ['Progresso', `${progress}%`]
        ];

        const metrics = $('#metrics');

        if (!metrics) {
            return;
        }

        metrics.innerHTML = values
            .map(
                ([label, value]) => `
                    <div class="metric">
                        <span>
                            ${escapeHtml(label)}
                        </span>

                        <strong>
                            ${escapeHtml(value ?? 0)}
                        </strong>
                    </div>
                `
            )
            .join('');
    } catch (error) {
        console.error(
            'Erro ao carregar estatísticas:',
            error
        );
    }
}

// ==========================================================
// FORMATAR DURAÇÃO
// ==========================================================

function formatDuration(seconds) {
    const total = Number(seconds);

    if (!Number.isFinite(total) || total <= 0) {
        return '—';
    }

    const minutes = Math.floor(total / 60);
    const remainingSeconds = Math.round(total % 60);

    return (
        `${minutes}:${String(remainingSeconds).padStart(2, '0')}`
    );
}

// ==========================================================
// DETALHES DA ANÁLISE
// ==========================================================

function buildDetailText(video) {
    if (video.error_message) {
        return video.error_message;
    }

    if (video.professor_name === 'Não identificado') {
        return 'Professor não confirmado (evidência insuficiente).';
    }

    return '';
}

// ==========================================================
// TOOLTIP DO MODELO DE AULA
// ==========================================================

function buildModelTooltip(modelName) {
    const key = String(modelName || '')
        .trim()
        .toLowerCase();

    const specification = MODEL_SPECIFICATIONS_BY_KEY[key];

    return specification
        ? `Modelo: ${specification}`
        : '';
}

// O atributo title nativo depende do tooltip do sistema
// operacional (atraso variável, pode ficar atrás de outros
// elementos, não é confiável em todos os navegadores/telas
// sensíveis ao toque). Para garantir que o tooltip realmente
// apareça, é desenhado aqui um balão próprio, posicionado via
// JS e anexado ao <body> — assim ele nunca é cortado pelo
// "overflow: auto" da tabela rolável (.table-wrap).
const modelTooltipElement = document.createElement('div');
modelTooltipElement.className = 'model-tooltip';
modelTooltipElement.setAttribute('role', 'tooltip');
document.body.appendChild(modelTooltipElement);

function positionModelTooltip(cell) {
    const cellRect = cell.getBoundingClientRect();

    modelTooltipElement.style.left = `${cellRect.left}px`;
    modelTooltipElement.style.top = `${cellRect.bottom + 6}px`;

    const tooltipRect =
        modelTooltipElement.getBoundingClientRect();

    if (tooltipRect.right > window.innerWidth - 8) {
        modelTooltipElement.style.left =
            `${Math.max(8, window.innerWidth - tooltipRect.width - 8)}px`;
    }

    if (tooltipRect.bottom > window.innerHeight - 8) {
        modelTooltipElement.style.top =
            `${cellRect.top - tooltipRect.height - 6}px`;
    }
}

function showModelTooltip(cell) {
    const text = cell.dataset.tooltip;

    if (!text) {
        return;
    }

    modelTooltipElement.textContent = text;
    modelTooltipElement.classList.add('show');
    positionModelTooltip(cell);
}

function hideModelTooltip() {
    modelTooltipElement.classList.remove('show');
}

if ($('#videos')) {
    const videosBody = $('#videos');

    videosBody.addEventListener('mouseover', (event) => {
        const cell = event.target.closest('.model-cell');

        if (!cell) {
            return;
        }

        showModelTooltip(cell);
    });

    videosBody.addEventListener('mouseout', (event) => {
        const cell = event.target.closest('.model-cell');

        if (!cell) {
            return;
        }

        if (
            event.relatedTarget &&
            cell.contains(event.relatedTarget)
        ) {
            return;
        }

        hideModelTooltip();
    });

    // Toque/clique: sem hover, o balão acima não aparece — o
    // toast (já usado no restante do projeto) garante acesso à
    // mesma especificação em telas sensíveis ao toque.
    videosBody.addEventListener('click', (event) => {
        const cell = event.target.closest('.model-cell');

        if (!cell || !cell.dataset.tooltip) {
            return;
        }

        toast(cell.dataset.tooltip);
    });
}

if ($('.table-wrap')) {
    $('.table-wrap').addEventListener(
        'scroll',
        hideModelTooltip
    );
}

// ==========================================================
// LINK DO VÍDEO NO JW PLAYER
// ==========================================================

function buildJWPlayerMediaUrl(jwplayerId) {
    const propertyId =
        getSelectedJWLibrary()?.propertyId ||
        state.jwPropertyId ||
        jwLibraries[DEFAULT_JW_LIBRARY].propertyId;

    return (
        `https://dashboard.jwplayer.com/p/${propertyId}` +
        `/media/${encodeURIComponent(jwplayerId)}`
    );
}

// ==========================================================
// VÍDEOS
// ==========================================================

// Ao iniciar uma nova execução (planilha ou individual), a
// Etapa 4 volta a mostrar somente essa execução (o backend
// já filtra por ela). Sem isso, um filtro de busca/status/
// modelo deixado de uma execução anterior poderia esconder
// os resultados da execução atual, parecendo lista vazia.
function resetResultsFilters() {
    const professorFilter = $('#professor-filter');
    const yearFilter = $('#year-filter');
    const statusFilter = $('#status-filter');
    const categoryFilter = $('#category-filter');

    if (professorFilter) {
        professorFilter.value = '';
    }

    if (yearFilter) {
        yearFilter.value = '';
    }

    if (statusFilter) {
        statusFilter.value = '';
    }

    if (categoryFilter) {
        categoryFilter.value = '';
    }
}

let loadedVideos = [];

function renderVideos(items) {
    const resultCount =
        $('#result-count');

    const videos =
        $('#videos');

    if (resultCount) {
        resultCount.textContent =
            `${items.length} registro(s)`;
    }

    if (!videos) {
        return;
    }

    videos.innerHTML = items
        .map(
            (video) => {
                const detailText =
                    buildDetailText(video);

                return `
                    <tr>
                        <td>
                            ${escapeHtml(
                                video.lesson_name ||
                                video.video ||
                                '—'
                            )}
                        </td>

                        <td>
                            ${escapeHtml(
                                video.professor_name ||
                                '—'
                            )}
                        </td>

                        <td
                            class="model-cell"
                            data-tooltip="${escapeHtml(
                                buildModelTooltip(
                                    video.final_category ||
                                    video.category
                                )
                            )}"
                        >
                            ${escapeHtml(
                                video.final_category ||
                                video.category ||
                                '—'
                            )}
                        </td>

                        <td>
                            ${escapeHtml(
                                video.summary ||
                                '—'
                            )}
                        </td>

                        <td>
                            ${escapeHtml(
                                formatDuration(video.duration)
                            )}
                        </td>

                        <td>
                            <span
                                class="badge ${escapeHtml(
                                    video.status ||
                                    'Pendente'
                                )}"
                            >
                                ${escapeHtml(
                                    video.status ||
                                    'Pendente'
                                )}
                            </span>
                        </td>

                        <td
                            class="detail-cell"
                            title="${escapeHtml(detailText)}"
                        >
                            ${escapeHtml(
                                detailText || '—'
                            )}
                        </td>

                        <td>
                            ${escapeHtml(
                                video.macrotema ||
                                'Não identificado'
                            )}
                        </td>

                        <td>
                            ${escapeHtml(
                                video.microtema ||
                                'Não identificado'
                            )}
                        </td>

                        <td>
                            ${escapeHtml(
                                video.nanotema ||
                                'Não identificado'
                            )}
                        </td>

                        <td>
                            ${video.jwplayer_id
                                ? `<a
                                    class="jwplayer-link"
                                    href="${escapeHtml(
                                        buildJWPlayerMediaUrl(
                                            video.jwplayer_id
                                        )
                                    )}"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                >${escapeHtml(
                                    video.jwplayer_id
                                )}</a>`
                                : '—'
                            }
                        </td>
                    </tr>
                `;
            }
        )
        .join('');
}

function publishDateYear(value) {
    const match = String(value || '').match(
        /^(\d{4})-\d{2}-\d{2}/
    );

    return match
        ? Number(match[1])
        : null;
}

const MIN_YEAR_FILTER = 2016;

function populateYearFilterOptions() {
    const yearFilter = $('#year-filter');

    if (!yearFilter) {
        return;
    }

    const currentYear = new Date().getFullYear();

    const maxYear = loadedVideos.reduce(
        (max, video) => {
            const year = publishDateYear(
                video.publish_date
            );

            return year && year > max
                ? year
                : max;
        },
        currentYear
    );

    const previousValue = yearFilter.value;

    const options = ['<option value="">Todos os anos</option>'];

    for (
        let year = MIN_YEAR_FILTER;
        year <= maxYear;
        year++
    ) {
        options.push(
            `<option value="${year}">${year}</option>`
        );
    }

    yearFilter.innerHTML = options.join('');
    yearFilter.value = previousValue;
}

function updateExportCsvLink() {
    const link = $('#download-csv');

    if (!link) {
        return;
    }

    const yearFilter = $('#year-filter');
    const year = yearFilter ? yearFilter.value : '';

    link.href = year
        ? `/api/export.csv?year=${encodeURIComponent(year)}`
        : '/api/export.csv';
}

// ==========================================================
// BUSCA GERAL (campo "Filtrar por professor")
// ==========================================================
//
// O campo de busca deixou de olhar somente para o nome do
// professor: agora ele varre, em conjunto, todos os campos
// relevantes de cada linha (professor, nome da aula, modelo/
// classificação, macrotema, microtema, nanotema, resumo e
// JWPlayer ID). Basta digitar um trecho de qualquer um desses
// campos para encontrar a linha.

function buildSearchableText(video) {
    return [
        video.professor_name,
        video.lesson_name,
        video.video,
        video.final_category,
        video.category,
        video.macrotema,
        video.microtema,
        video.nanotema,
        video.summary,
        video.jwplayer_id
    ]
        .filter(Boolean)
        .join(' \u0000 ')
        .toLowerCase();
}

function applyResultFilters() {
    const professorFilter = $('#professor-filter');
    const yearFilter = $('#year-filter');

    const needle =
        professorFilter
            ? professorFilter.value.trim().toLowerCase()
            : '';

    const year = yearFilter
        ? yearFilter.value
        : '';

    const items = loadedVideos.filter((video) => {
        const matchesSearch =
            !needle ||
            buildSearchableText(video).includes(needle);

        const matchesYear =
            !year ||
            publishDateYear(video.publish_date) ===
                Number(year);

        return matchesSearch && matchesYear;
    });

    renderVideos(items);
    updateExportCsvLink();
}

async function loadVideos() {
    const statusFilter = $('#status-filter');
    const categoryFilter = $('#category-filter');

    if (
        !statusFilter ||
        !categoryFilter
    ) {
        return;
    }

    const query = new URLSearchParams({
        status: statusFilter.value || '',
        category: categoryFilter.value || ''
    });

    try {
        const data =
            await api(
                `/api/videos?${query.toString()}`
            );

        loadedVideos =
            Array.isArray(data.items)
                ? data.items
                : [];

        populateYearFilterOptions();
        applyResultFilters();
    } catch (error) {
        console.error(
            'Erro ao carregar vídeos:',
            error
        );
    }
}

// ==========================================================
// FILTROS
// ==========================================================

if ($('#professor-filter')) {
    $('#professor-filter').addEventListener(
        'input',
        applyResultFilters
    );
}

if ($('#year-filter')) {
    $('#year-filter').addEventListener(
        'change',
        applyResultFilters
    );
}

if ($('#status-filter')) {
    $('#status-filter').addEventListener(
        'change',
        loadVideos
    );
}

if ($('#category-filter')) {
    $('#category-filter').addEventListener(
        'change',
        loadVideos
    );
}

// ==========================================================
// CONEXÃO JW PLAYER
// ==========================================================

function applyConnection(status = {}) {
    const selectedLibrary =
        getSelectedJWLibrary();

    const selectedPropertyId =
        String(
            selectedLibrary?.propertyId || ''
        ).trim();

    let returnedPropertyId =
        String(
            status.property_id ||
            status.propertyId ||
            ''
        ).trim();

    if (!returnedPropertyId) {
        returnedPropertyId =
            extractPropertyIdFromUrl(
                status.current_url ||
                status.url ||
                ''
            );
    }

    const isConnected =
        status.state === 'connected' ||
        status.connected === true;

    const correctLibrary =
        !returnedPropertyId ||
        !selectedPropertyId ||
        returnedPropertyId.toUpperCase() ===
            selectedPropertyId.toUpperCase();

    state.connected = Boolean(
        isConnected &&
        correctLibrary
    );

    state.jwPropertyId =
        selectedPropertyId;

    state.jwLibrary =
        getSelectedJWLibraryKey();

    const miniDot =
        $('#mini-dot');

    const miniStatus =
        $('#mini-status');

    if (miniDot) {
        miniDot.classList.toggle(
            'connected',
            state.connected
        );
    }

    if (miniStatus) {
        miniStatus.textContent =
            state.connected
                ? (
                    selectedLibrary
                        ? `JW ${selectedLibrary.name} conectada`
                        : 'Biblioteca JW conectada'
                )
                : 'JW Player desconectado';
    }

    const statusIcon =
        $('#status-icon');

    if (statusIcon) {
        statusIcon.classList.toggle(
            'connected',
            state.connected
        );
    }

    const connectionTitle =
        $('#connection-title');

    if (connectionTitle) {
        if (state.connected) {
            connectionTitle.textContent =
                selectedLibrary
                    ? `Biblioteca ${selectedLibrary.name} conectada`
                    : 'Biblioteca conectada';
        } else if (
            status.state === 'attention'
        ) {
            connectionTitle.textContent =
                'Verificação necessária';
        } else if (
            status.state === 'connecting'
        ) {
            connectionTitle.textContent =
                'Conectando...';
        } else {
            connectionTitle.textContent =
                'Não conectado';
        }
    }

    const connectionMessage =
        $('#connection-message');

    if (connectionMessage) {
        if (
            isConnected &&
            !correctLibrary
        ) {
            const backendLibrary =
                status.library_name ||
                status.library ||
                returnedPropertyId ||
                'outra biblioteca';

            connectionMessage.textContent =
                `A sessão está conectada à biblioteca ${backendLibrary}, mas a biblioteca selecionada é ${selectedLibrary?.name || 'outra biblioteca'}.`;
        } else {
            connectionMessage.textContent =
                status.message ||
                (
                    selectedLibrary
                        ? `Selecione ${selectedLibrary.name} e conecte sua conta JW Player.`
                        : 'Selecione uma biblioteca JW Player.'
                );
        }
    }

    const continueImport =
        $('#continue-import');

    if (continueImport) {
        continueImport.disabled =
            !state.connected;
    }

    updateAnalysisButtons();

    const importLock =
        $('#import-lock');

    if (importLock) {
        importLock.classList.toggle(
            'unlocked',
            state.connected
        );

        importLock.textContent =
            state.connected
                ? 'Biblioteca conectada. Selecione uma planilha ou informe um JWPlayer ID.'
                : 'Conecte primeiro a biblioteca JW Player para liberar esta etapa.';
    }

    updateJWLibraryLink();
}

// ==========================================================
// TROCAR DE BIBLIOTECA (MESMA SESSÃO JW PLAYER)
// ==========================================================
//
// As bibliotecas pertencem à mesma conta JW Player: trocar de
// biblioteca não é um novo login, é só mudar o contexto/property
// da pesquisa. Reaproveita a sessão já conectada em segundo
// plano (/api/jw/switch-library) — não envia e-mail nem senha.
// Só resulta em "desconectado" quando a sessão realmente não
// está mais válida, e nesse caso o usuário pode reconectar
// normalmente pelo formulário de login.

async function switchJWLibrary(library, libraryKey) {
    try {
        const status =
            await api(
                '/api/jw/switch-library',
                {
                    method: 'POST',

                    headers: {
                        'Content-Type':
                            'application/json'
                    },

                    body: JSON.stringify({
                        property_id:
                            library.propertyId,

                        library:
                            libraryKey
                    })
                }
            );

        applyConnection(status);

        return status;
    } catch (error) {
        applyConnection({
            state: 'disconnected',

            property_id:
                library.propertyId,

            library:
                libraryKey,

            message:
                error.message ||
                'Erro ao trocar de biblioteca no JW Player.'
        });

        return null;
    }
}

// ==========================================================
// VERIFICAR STATUS DO JW PLAYER
// ==========================================================

async function checkJWStatus() {
    const library =
        getSelectedJWLibrary();

    const libraryKey =
        getSelectedJWLibraryKey();

    try {
        const query =
            new URLSearchParams({
                property_id:
                    library?.propertyId || '',

                library:
                    libraryKey || ''
            });

        const status =
            await api(
                `/api/jw/status?${query.toString()}`
            );

        applyConnection(status);

        return status;
    } catch (error) {
        applyConnection({
            state: 'disconnected',

            property_id:
                library?.propertyId || '',

            library:
                libraryKey || '',

            message:
                error.message ||
                'Erro ao checar status da sessão do JW Player.'
        });

        return null;
    }
}

// ==========================================================
// LOGIN / CONEXÃO NO JW PLAYER
// ==========================================================

async function loginJW() {
    const library =
        getSelectedJWLibrary();

    const libraryKey =
        getSelectedJWLibraryKey();

    if (!library || !libraryKey) {
        toast(
            'Selecione uma biblioteca do JW Player.'
        );

        return;
    }

    const emailInput =
        $('#jw-email');

    const passwordInput =
        $('#jw-password');

    const email =
        String(emailInput?.value || '').trim();

    const password =
        String(passwordInput?.value || '');

    if (!email || !password) {
        toast(
            'Informe e-mail e senha do JW Player.'
        );

        return;
    }

    const button =
        $('#jw-login');

    if (button) {
        button.disabled = true;
    }

    applyConnection({
        state: 'connecting',

        property_id:
            library.propertyId,

        library:
            libraryKey,

        message:
            `Conectando à biblioteca ${library.name} em segundo plano...`
    });

    try {
        const result =
            await api(
                '/api/jw/login',
                {
                    method: 'POST',

                    headers: {
                        'Content-Type':
                            'application/json'
                    },

                    body: JSON.stringify({
                        property_id:
                            library.propertyId,

                        library:
                            libraryKey,

                        email,

                        password
                    })
                }
            );

        applyConnection(result);

        if (
            result.state === 'connected' ||
            result.connected === true
        ) {
            toast(
                `Conectado à biblioteca ${library.name} com sucesso!`
            );

            if (passwordInput) {
                passwordInput.value = '';
            }
        } else if (result.message) {
            toast(result.message);
        }
    } catch (error) {
        applyConnection({
            state: 'error',

            property_id:
                library.propertyId,

            library:
                libraryKey,

            message:
                error.message ||
                'Erro ao conectar ao JW Player.'
        });

        toast(
            error.message ||
            'Erro ao realizar conexão com o JW Player.'
        );
    } finally {
        if (button) {
            button.disabled = false;
        }
    }
}

const jwLoginForm =
    $('#login-form');

if (jwLoginForm) {
    jwLoginForm.addEventListener(
        'submit',
        (event) => {
            event.preventDefault();

            loginJW();
        }
    );
}

const verifySessionBtn =
    $('#verify-session');

if (verifySessionBtn) {
    verifySessionBtn.addEventListener(
        'click',
        async () => {
            verifySessionBtn.disabled = true;

            try {
                await checkJWStatus();
            } finally {
                verifySessionBtn.disabled = false;
            }
        }
    );
}

// ==========================================================
// SESSÃO EXPIRADA
// ==========================================================

function isSessionError(message) {
    return String(message || '')
        .toLowerCase()
        .includes('conecte');
}

async function handleSessionExpired(message) {
    toast(
        message ||
        'A sessão do JW Player expirou. Conecte novamente.'
    );

    show('connection');

    await checkJWStatus();
}



function getPublishDateFilter() {
    const enabled =
        $('#enable-publish-filter')?.checked ||
        false;

    const dateValue =
        $('#min-publish-date')?.value ||
        '';

    const includeMissingDate =
        $('#include-missing-date')?.checked ||
        false;

    return {
        min_publish_date:
            enabled ? dateValue : '',

        include_missing_date:
            includeMissingDate
    };
}

function renderFilterSummary(filter) {
    const container =
        $('#filter-summary');

    if (!container || !filter) {
        return;
    }

    container.innerHTML = `
        <div class="alert alert-success">
            <strong>${escapeHtml(filter.total)} vídeo(s) verificado(s)</strong><br>

            ${escapeHtml(filter.eligible)} dentro do período<br>
            ${escapeHtml(filter.filtered)} anteriores à data mínima<br>
            ${escapeHtml(filter.no_date)} sem data de publicação<br>
            ${escapeHtml(filter.errors)} com erro na consulta ao JW Player<br>
            <br>
            <strong>
                ${escapeHtml(filter.will_be_analyzed)}
                vídeo(s) serão enviados para análise.
            </strong>
        </div>
    `;

    const startButton =
        $('#start-eligible');

    if (startButton) {
        startButton.style.display =
            filter.will_be_analyzed > 0
                ? ''
                : 'none';
    }
}

// ==========================================================
// PROCESSAMENTO / UPLOAD DE PLANILHA
// ==========================================================

async function processFile() {
    const fileInput =
        $('#spreadsheet');

    const importResult =
        $('#import-result');

    if (
        !fileInput ||
        !fileInput.files.length
    ) {
        toast(
            'Selecione um arquivo de planilha para importar.'
        );

        return;
    }

    if (!state.connected) {
        toast(
            'Conecte-se ao JW Player antes de importar.'
        );

        return;
    }

    const library =
        getSelectedJWLibrary();

    const libraryKey =
        getSelectedJWLibraryKey();

    const formData =
        new FormData();

    formData.append(
        'file',
        fileInput.files[0]
    );

    formData.append(
        'property_id',
        library?.propertyId ||
        state.jwPropertyId
    );

    formData.append(
        'library',
        libraryKey ||
        state.jwLibrary
    );

    const providerSelect =
        $('#provider');

    const modelSelect =
        $('#ai-model');

    const framesInput =
        $('#frame-count');

    const analysisModeSelect =
        $('#analysis-mode');

    const whisperSelect =
        $('#whisper-model');

    if (providerSelect) {
        formData.append(
            'provider',
            providerSelect.value
        );
    }

    if (modelSelect) {
        formData.append(
            'model',
            modelSelect.value
        );
    }

    if (framesInput) {
        formData.append(
            'frame_count',
            framesInput.value
        );
    }

    if (analysisModeSelect) {
        formData.append(
            'analysis_mode',
            analysisModeSelect.value
        );
    }

    if (
        whisperSelect &&
        analysisModeSelect?.value === 'hybrid'
    ) {
        formData.append(
            'whisper_model',
            whisperSelect.value
        );
    }

    const publishFilter =
        getPublishDateFilter();

    formData.append(
        'min_publish_date',
        publishFilter.min_publish_date
    );

    formData.append(
        'include_missing_date',
        publishFilter.include_missing_date
    );

    if (importResult) {
        importResult.innerHTML =
            '<div class="loading">Importando planilha e consultando datas de publicação no JW Player...</div>';
    }

    const filterSummaryEl =
        $('#filter-summary');

    if (filterSummaryEl) {
        filterSummaryEl.innerHTML = '';
    }

    const startButton =
        $('#start-eligible');

    if (startButton) {
        startButton.style.display = 'none';
    }

    try {
        const response =
            await fetch(
                '/api/import-and-process',
                {
                    method: 'POST',
                    body: formData
                }
            );

        const data =
            await response.json();

        if (!response.ok) {
            throw new Error(
                data.detail ||
                data.message ||
                'Erro ao processar arquivo.'
            );
        }

        if (importResult) {
            importResult.innerHTML = `
                <div class="alert alert-success">
                    <strong>Planilha importada!</strong><br>
                    Arquivo:
                    ${escapeHtml(
                        fileInput.files[0].name
                    )}<br>

                    Vídeos pendentes:
                    ${escapeHtml(
                        data.pending_media ?? 0
                    )}
                </div>
            `;
        }

        renderFilterSummary(
            data.filter
        );

        toast(
            'Planilha importada com sucesso! ' +
            'Revise o resumo abaixo antes de iniciar a análise.'
        );

        loadStats();
        loadVideos();
    } catch (error) {
        if (importResult) {
            importResult.innerHTML = `
                <div class="alert alert-danger">
                    <strong>Erro no envio:</strong>
                    ${escapeHtml(error.message)}
                </div>
            `;
        }

        if (isSessionError(error.message)) {
            await handleSessionExpired(error.message);
        } else {
            toast(
                `Erro: ${error.message}`
            );
        }
    }
}

// ==========================================================
// INICIAR ANÁLISE (SOMENTE VÍDEOS ELEGÍVEIS)
// ==========================================================

async function startEligibleAnalysis() {
    const startButton =
        $('#start-eligible');

    const providerSelect =
        $('#provider');

    const modelSelect =
        $('#ai-model');

    const framesInput =
        $('#frame-count');

    const analysisModeSelect =
        $('#analysis-mode');

    const whisperSelect =
        $('#whisper-model');

    const payload = {
        provider:
            providerSelect?.value ||
            'Gemini',

        model:
            modelSelect?.value ||
            providerDefaults.Gemini,

        frame_count:
            Number(
                framesInput?.value || 8
            ),

        analysis_mode:
            analysisModeSelect?.value ||
            'frames',

        whisper_model:
            whisperSelect?.value ||
            'small'
    };

    if (startButton) {
        startButton.disabled = true;
    }

    try {
        const result =
            await api(
                '/api/start-eligible',
                {
                    method: 'POST',

                    headers: {
                        'Content-Type':
                            'application/json'
                    },

                    body:
                        JSON.stringify(payload)
                }
            );

        toast(
            `Análise iniciada para ${result.media_count ?? 0} vídeo(s) elegível(is).`
        );

        if (startButton) {
            startButton.style.display = 'none';
        }

        resetResultsFilters();
        loadStats();
        loadVideos();
        loadJobs();

        show('processing');
    } catch (error) {
        if (isSessionError(error.message)) {
            await handleSessionExpired(error.message);
        } else {
            toast(
                `Erro ao iniciar análise: ${error.message}`
            );
        }
    } finally {
        if (startButton) {
            startButton.disabled = false;
        }
    }
}

if ($('#start-eligible')) {
    $('#start-eligible').addEventListener(
        'click',
        startEligibleAnalysis
    );
}

const uploadBtn =
    $('#upload');

if (uploadBtn) {
    uploadBtn.addEventListener(
        'click',
        processFile
    );
}

const spreadsheetInput =
    $('#spreadsheet');

if (spreadsheetInput) {
    spreadsheetInput.addEventListener(
        'change',
        updateAnalysisButtons
    );
}

// ==========================================================
// ACOMPANHAR JOB ATÉ CONCLUIR
// ==========================================================

const TERMINAL_JOB_STATES = [
    'completed',
    'error',
    'cancelled'
];

async function findJob(jobId) {
    const data = await api('/api/jobs');

    const items =
        Array.isArray(data?.items)
            ? data.items
            : [];

    return items.find(
        (item) => item.id === jobId
    ) || null;
}

async function pollJobUntilDone(
    jobId,
    onProgress,
    {
        intervalMs = 2000,
        timeoutMs = 15 * 60 * 1000
    } = {}
) {
    const startedAt = Date.now();

    while (Date.now() - startedAt < timeoutMs) {
        const job = await findJob(jobId);

        if (job && TERMINAL_JOB_STATES.includes(job.state)) {
            return job;
        }

        if (job && onProgress) {
            onProgress(job);
        }

        await new Promise(
            (resolve) => setTimeout(resolve, intervalMs)
        );
    }

    return null;
}

function renderSingleProgress(job) {
    const singleResult =
        $('#single-id-result');

    if (!singleResult) {
        return;
    }

    singleResult.innerHTML = `
        <div class="card result-card">
            <p class="job-stage">
                ${escapeHtml(
                    job.stage || 'Processando'
                )}
            </p>

            <small>
                ${escapeHtml(job.message || '')}
            </small>
        </div>
    `;
}

function renderSingleResult(job, jwId, payload) {
    const singleResult =
        $('#single-id-result');

    if (!singleResult) {
        return;
    }

    if (job.state === 'completed') {
        const result =
            job.result || {};

        singleResult.innerHTML = `
            <div class="card result-card">

                <h3>Resultado da análise</h3>

                <p>
                    <strong>JWPlayer ID:</strong>
                    ${escapeHtml(job.jwplayer_id || jwId)}
                </p>

                <p>
                    <strong>Título:</strong>
                    ${escapeHtml(result.title || '—')}
                </p>

                <p>
                    <strong>Classificação:</strong>
                    ${escapeHtml(result.category || '—')}
                </p>

                <p>
                    <strong>Professor:</strong>
                    ${escapeHtml(result.professor_name || '—')}
                </p>

                <p>
                    <strong>Resumo:</strong>
                    ${escapeHtml(result.summary || '—')}
                </p>

                <p>
                    <strong>Duração:</strong>
                    ${escapeHtml(formatDuration(result.duration))}
                </p>

                <p>
                    <strong>Provedor / Modelo:</strong>
                    ${escapeHtml(payload.provider)} / ${escapeHtml(payload.model)}
                </p>

                <p>
                    <strong>Status:</strong>
                    <span class="badge Concluído">Concluído</span>
                </p>

            </div>
        `;

        toast('Análise concluída!');

        return;
    }

    singleResult.innerHTML = `
        <div class="alert alert-danger">
            <strong>
                ${escapeHtml(
                    job.state === 'cancelled'
                        ? 'Análise cancelada'
                        : 'Erro na análise'
                )}
                ${job.stage ? ` (${escapeHtml(job.stage)})` : ''}:
            </strong>
            ${escapeHtml(job.message || 'Falha desconhecida.')}
        </div>
    `;

    toast(job.message || 'Erro na análise.');
}

// ==========================================================
// ANÁLISE INDIVIDUAL POR JWPLAYER ID
// ==========================================================

async function analyzeSingleJWPlayer() {
    const input =
        $('#single-jwplayer-id');

    const singleResult =
        $('#single-id-result');

    const jwId =
        String(
            input?.value || ''
        ).trim();

    if (!isValidJWPlayerId(jwId)) {
        toast(
            'Informe um JWPlayer ID válido (8 caracteres).'
        );

        return;
    }

    if (!state.connected) {
        toast(
            'Conecte-se ao JW Player para analisar.'
        );

        return;
    }

    const library =
        getSelectedJWLibrary();

    const libraryKey =
        getSelectedJWLibraryKey();

    if (!library || !libraryKey) {
        toast(
            'Selecione uma biblioteca JW Player.'
        );

        return;
    }

    state.analyzingSingle = true;

    updateAnalysisButtons();

    if (singleResult) {
        singleResult.innerHTML =
            '<div class="loading">Validando e enviando vídeo para análise...</div>';
    }

    const providerSelect =
        $('#provider');

    const modelSelect =
        $('#ai-model');

    const framesInput =
        $('#frame-count');

    const analysisModeSelect =
        $('#analysis-mode');

    const whisperSelect =
        $('#whisper-model');

    const payload = {
        jwplayer_id:
            jwId,

        property_id:
            library.propertyId,

        library:
            libraryKey,

        provider:
            providerSelect?.value ||
            'Gemini',

        model:
            modelSelect?.value ||
            providerDefaults.Gemini,

        frame_count:
            Number(
                framesInput?.value || 8
            ),

        analysis_mode:
            analysisModeSelect?.value ||
            'frames',

        whisper_model:
            whisperSelect?.value ||
            'small',

        ...getPublishDateFilter()
    };

    try {
        const enqueueResult =
            await api(
                '/api/analyze-jwplayer',
                {
                    method: 'POST',

                    headers: {
                        'Content-Type':
                            'application/json'
                    },

                    body:
                        JSON.stringify(payload)
                }
            );

        const job =
            Array.isArray(enqueueResult.jobs)
                ? enqueueResult.jobs[0]
                : null;

        loadStats();
        loadJobs();

        if (!job?.id) {
            toast(
                enqueueResult.message ||
                'Vídeo enviado para análise.'
            );

            return;
        }

        renderSingleProgress(job);

        const finalJob =
            await pollJobUntilDone(
                job.id,
                (progressJob) => {
                    renderSingleProgress(progressJob);
                    loadJobs();
                }
            );

        resetResultsFilters();
        loadStats();
        loadVideos();
        loadJobs();

        if (!finalJob) {
            if (singleResult) {
                singleResult.innerHTML = `
                    <div class="card result-card">
                        <p>
                            A análise ainda está em andamento.
                            Acompanhe o progresso na Etapa 3.
                        </p>
                    </div>
                `;
            }

            show('processing');

            return;
        }

        renderSingleResult(finalJob, jwId, payload);
    } catch (error) {
        if (singleResult) {
            singleResult.innerHTML = `
                <div class="alert alert-danger">
                    <strong>Erro na análise:</strong>
                    ${escapeHtml(
                        error.message
                    )}
                </div>
            `;
        }

        if (isSessionError(error.message)) {
            await handleSessionExpired(error.message);
        } else {
            toast(
                `Erro na análise: ${error.message}`
            );
        }
    } finally {
        state.analyzingSingle = false;

        updateAnalysisButtons();
    }
}

const analyzeSingleBtn =
    $('#analyze-single-id');

if (analyzeSingleBtn) {
    analyzeSingleBtn.addEventListener(
        'click',
        analyzeSingleJWPlayer
    );
}

const singleJwInput =
    $('#single-jwplayer-id');

if (singleJwInput) {
    singleJwInput.addEventListener(
        'input',
        updateAnalysisButtons
    );
}

// ==========================================================
// GERENCIAMENTO DE JOBS
// ==========================================================

async function loadJobs() {
    const jobsList =
        $('#jobs');

    if (!jobsList) {
        return;
    }

    try {
        const data =
            await api('/api/jobs');

        const jobs =
            Array.isArray(data?.items)
                ? data.items
                : [];

        if (!jobs.length) {
            jobsList.innerHTML =
                '<div class="empty">Nenhum trabalho iniciado.</div>';

            return;
        }

        jobsList.innerHTML =
            [...jobs]
                .reverse()
                .map(
                    (job) => {
                        const state =
                            job.state ||
                            'queued';

                        const stage =
                            job.stage ||
                            '';

                        return `
                            <div class="job">

                                <header class="job-header">

                                    <strong>
                                        ${escapeHtml(
                                            job.jwplayer_id ||
                                            job.media_id ||
                                            '—'
                                        )}
                                    </strong>

                                    <span class="badge ${escapeHtml(state)}">
                                        ${escapeHtml(state)}
                                    </span>

                                </header>

                                ${
                                    stage
                                        ? `<div class="job-stage">${escapeHtml(stage)}</div>`
                                        : ''
                                }

                                <small>
                                    ${escapeHtml(
                                        job.message ||
                                        ''
                                    )}
                                </small>

                            </div>
                        `;
                    }
                )
                .join('');
    } catch (error) {
        jobsList.innerHTML = `
            <div class="error-text">
                Erro ao carregar jobs:
                ${escapeHtml(
                    error.message
                )}
            </div>
        `;
    }
}

function startJobsAutoRefresh() {
    if (state.jobsTimer) {
        clearInterval(
            state.jobsTimer
        );
    }

    state.jobsTimer =
        setInterval(
            () => {
                loadJobs();
                loadStats();


                loadVideos();
            },
            5000
        );
}

// ==========================================================
// CONTINUAR DA CONEXÃO PARA IMPORTAÇÃO
// ==========================================================

const continueImportBtn =
    $('#continue-import');

if (continueImportBtn) {
    continueImportBtn.addEventListener(
        'click',
        () => {
            if (!state.connected) {
                toast(
                    'Conecte primeiro ao JW Player.'
                );

                return;
            }

            show('import');
        }
    );
}

// ==========================================================
// CONFIGURAÇÃO DOS PROVEDORES DE IA
// ==========================================================

const aiProviderSelect =
    $('#provider');

const aiModelSelect =
    $('#ai-model');

if (
    aiProviderSelect &&
    aiModelSelect
) {
    aiProviderSelect.addEventListener(
        'change',
        () => {
            const selectedProvider =
                aiProviderSelect.value;

            const defaultModel =
                providerDefaults[
                    selectedProvider
                ];

            if (defaultModel) {
                aiModelSelect.value =
                    defaultModel;
            }
        }
    );
}

const analysisModeToggle =
    $('#analysis-mode');

const whisperLabel =
    $('#whisper-label');

if (analysisModeToggle && whisperLabel) {
    const toggleWhisperVisibility = () => {
        whisperLabel.style.display =
            analysisModeToggle.value === 'hybrid'
                ? ''
                : 'none';
    };

    analysisModeToggle.addEventListener(
        'change',
        toggleWhisperVisibility
    );

    toggleWhisperVisibility();
}

// ==========================================================
// INICIALIZAÇÃO DA APLICAÇÃO
// ==========================================================

document.addEventListener(
    'DOMContentLoaded',
    async () => {
        initializeJWProperties();

        registerJWLibraryChange();

        updateAnalysisButtons();

        applyServiceStatus();

        applyConnection({
            state: 'disconnected',
            message:
                'Verificando sessão do JW Player...'
        });

        await checkJWStatus();

        loadStats();
        loadVideos();
        loadJobs();

        startJobsAutoRefresh();
    }
);