/* Widget del asistente de chat (SGR - Municipalidad de La Serena).
   Se carga solo para Admin, Coordinador, Delegado y superusuario. */
(function () {
    'use strict';

    var widget = document.getElementById('chatbotWidget');
    if (!widget) { return; }

    var boton = document.getElementById('chatbotBoton');
    var panel = document.getElementById('chatbotPanel');
    var cerrar = document.getElementById('chatbotCerrar');
    var limpiar = document.getElementById('chatbotLimpiar');
    var formulario = document.getElementById('chatbotForm');
    var texto = document.getElementById('chatbotTexto');
    var enviar = document.getElementById('chatbotEnviar');
    var mensajes = document.getElementById('chatbotMensajes');
    var escribiendo = document.getElementById('chatbotEscribiendo');
    var token = formulario.querySelector('input[name="csrfmiddlewaretoken"]');

    var urlMensaje = widget.dataset.urlMensaje;
    var urlHistorial = widget.dataset.urlHistorial;
    var urlLimpiar = widget.dataset.urlLimpiar;
    var maxMensaje = parseInt(widget.dataset.maxMensaje, 10) || 2000;
    var historialCargado = false;
    var esperando = false;

    function peticionJson(url, opciones) {
        opciones = opciones || {};
        opciones.headers = opciones.headers || {};
        opciones.headers['X-CSRFToken'] = token ? token.value : '';
        opciones.headers['X-Requested-With'] = 'XMLHttpRequest';
        if (opciones.body) { opciones.headers['Content-Type'] = 'application/json'; }
        opciones.credentials = 'same-origin';
        return fetch(url, opciones).then(function (respuesta) {
            return respuesta.json().catch(function () { return {}; }).then(function (datos) {
                if (!respuesta.ok) {
                    var error = new Error(datos.error || 'No se pudo completar la operación.');
                    error.datos = datos;
                    throw error;
                }
                return datos;
            });
        });
    }

    function alFinal() {
        mensajes.scrollTop = mensajes.scrollHeight;
    }

    function quitarVacio() {
        var vacio = mensajes.querySelector('.chatbot-vacio');
        if (vacio) { vacio.remove(); }
    }

    function agregarBurbuja(emisor, contenido) {
        quitarVacio();
        var burbuja = document.createElement('div');
        burbuja.className = 'chatbot-burbuja ' + (emisor === 'ASISTENTE' ? 'chatbot-burbuja-asistente' : 'chatbot-burbuja-usuario');
        var parrafo = document.createElement('p');
        parrafo.className = 'mb-0';           // textContent: el texto nunca se interpreta como HTML (evita XSS)
        parrafo.textContent = contenido;
        burbuja.appendChild(parrafo);
        mensajes.appendChild(burbuja);
        alFinal();
    }

    function agregarError(mensaje) {
        quitarVacio();
        var alerta = document.createElement('div');
        alerta.className = 'alert alert-warning py-1 px-2 mb-0 small chatbot-error';
        alerta.setAttribute('role', 'alert');
        alerta.textContent = mensaje;
        mensajes.appendChild(alerta);
        alFinal();
    }

    function mostrarEscribiendo(mostrar) {
        escribiendo.classList.toggle('d-none', !mostrar);
        if (mostrar) { alFinal(); }
    }

    function bloquear(estado) {
        esperando = estado;
        enviar.disabled = estado;
        texto.disabled = estado;
    }

    function cargarHistorial() {
        if (historialCargado) { return Promise.resolve(); }
        historialCargado = true;
        return peticionJson(urlHistorial, { method: 'GET' }).then(function (datos) {
            (datos.mensajes || []).forEach(function (mensaje) {
                agregarBurbuja(mensaje.emisor, mensaje.contenido);
            });
            alFinal();
        }).catch(function (error) {
            historialCargado = false;   // permite reintentar la próxima vez que se abra
            agregarError(error.message);
        });
    }

    function abrir() {
        panel.classList.remove('d-none');
        boton.setAttribute('aria-expanded', 'true');
        boton.classList.add('chatbot-boton-oculto');
        cargarHistorial();
        texto.focus();
    }

    function cerrarPanel() {
        panel.classList.add('d-none');
        boton.setAttribute('aria-expanded', 'false');
        boton.classList.remove('chatbot-boton-oculto');
    }

    function enviarMensaje() {
        var contenido = texto.value.trim();
        if (!contenido || esperando) { return; }
        if (contenido.length > maxMensaje) {
            agregarError('El mensaje no puede superar los ' + maxMensaje + ' caracteres.');
            return;
        }

        agregarBurbuja('USUARIO', contenido);
        texto.value = '';
        texto.style.height = 'auto';
        bloquear(true);
        mostrarEscribiendo(true);

        peticionJson(urlMensaje, { method: 'POST', body: JSON.stringify({ mensaje: contenido }) })
            .then(function (datos) {
                mostrarEscribiendo(false);
                agregarBurbuja('ASISTENTE', datos.respuesta);
            })
            .catch(function (error) {
                mostrarEscribiendo(false);
                agregarError(error.message);
            })
            .finally(function () {
                bloquear(false);
                texto.focus();
            });
    }

    boton.addEventListener('click', function () {
        if (panel.classList.contains('d-none')) { abrir(); } else { cerrarPanel(); }
    });

    cerrar.addEventListener('click', cerrarPanel);

    formulario.addEventListener('submit', function (evento) {
        evento.preventDefault();
        enviarMensaje();
    });

    texto.addEventListener('keydown', function (evento) {
        if (evento.key === 'Enter' && !evento.shiftKey) {
            evento.preventDefault();
            enviarMensaje();
        }
    });

    // El textarea crece con el texto, hasta un máximo
    texto.addEventListener('input', function () {
        texto.style.height = 'auto';
        texto.style.height = Math.min(texto.scrollHeight, 96) + 'px';
    });

    limpiar.addEventListener('click', function () {
        if (esperando) { return; }
        var confirmar = window.Swal
            ? Swal.fire({
                title: '¿Nueva conversación?',
                text: 'Se borrará el historial guardado de este asistente.',
                icon: 'question',
                showCancelButton: true,
                confirmButtonText: 'Sí, borrar',
                cancelButtonText: 'Cancelar',
                confirmButtonColor: '#AD0000',
                reverseButtons: true
            }).then(function (resultado) { return resultado.isConfirmed; })
            : Promise.resolve(window.confirm('¿Borrar el historial de esta conversación?'));

        confirmar.then(function (confirmado) {
            if (!confirmado) { return; }
            peticionJson(urlLimpiar, { method: 'POST' }).then(function () {
                mensajes.innerHTML = '';
                var vacio = document.createElement('div');
                vacio.className = 'chatbot-vacio text-muted text-center small p-3';
                vacio.textContent = 'Conversación nueva. ¿En qué puedo ayudarte?';
                mensajes.appendChild(vacio);
            }).catch(function (error) {
                agregarError(error.message);
            });
        });
    });
})();
