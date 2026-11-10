/*
 * Validaciones al escribir (SGR). Repiten en el navegador lo que el servidor revisa al guardar
 * (UsuarioApp/funciones.py: limpiar_rut, validar_rut y normalizar_telefono): así el error se ve antes de enviar.
 *  - <input data-rut>: RUT chileno con dígito verificador por módulo 11. Al salir del campo queda 22.043.402-8.
 *  - <input data-telefono>: teléfono chileno de 9 dígitos, con o sin +56. Al salir queda +56 9 1234 5678.
 *  - data-rut="solo-aviso" (login): marca el error, pero no impide enviar, por si una cuenta antigua no usa RUT.
 * Un campo vacío no se marca: si es obligatorio, lo dice el servidor.
 */
(function () {
    'use strict';

    // Paso 1: limpiar el RUT (sin puntos, espacios ni guion)
    function limpiarRut(rut) {
        return (rut || '').replace(/[.\s-]/g, '').toUpperCase();
    }

    // Pasos 2 a 7: separar el dígito verificador, multiplicar por 2..7 de derecha a izquierda, sumar y módulo 11
    function digitoVerificador(numero) {
        var suma = 0;
        var multiplicador = 2;
        for (var i = numero.length - 1; i >= 0; i--) {
            suma += parseInt(numero.charAt(i), 10) * multiplicador;
            multiplicador = multiplicador === 7 ? 2 : multiplicador + 1;
        }
        var resultado = 11 - (suma % 11);
        if (resultado === 11) { return '0'; }
        if (resultado === 10) { return 'K'; }
        return String(resultado);
    }

    function rutValido(rut) {
        var limpio = limpiarRut(rut);
        if (limpio.length < 2) { return false; }
        var numero = limpio.slice(0, -1);
        var dv = limpio.slice(-1);
        return /^\d+$/.test(numero) && digitoVerificador(numero) === dv;
    }

    // 22043402-8 -> 22.043.402-8
    function formatearRut(rut) {
        var limpio = limpiarRut(rut);
        var numero = limpio.slice(0, -1).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
        return numero + '-' + limpio.slice(-1);
    }

    // Teléfono: 9 dígitos que no parten en 0 ni 1; acepta el prefijo 56. Devuelve null si no es válido
    function normalizarTelefono(telefono) {
        var digitos = (telefono || '').replace(/\D/g, '');
        if (digitos.length === 11 && digitos.indexOf('56') === 0) { digitos = digitos.slice(2); }
        if (digitos.length !== 9 || '01'.indexOf(digitos.charAt(0)) !== -1) { return null; }
        return '+56 ' + digitos.charAt(0) + ' ' + digitos.slice(1, 5) + ' ' + digitos.slice(5);
    }

    // Mensaje de error propio, junto al campo (Bootstrap lo muestra cuando el campo tiene is-invalid)
    function marcar(campo, mensaje) {
        var aviso = campo.parentNode.querySelector('.aviso-validacion');
        if (!mensaje) {
            campo.classList.remove('is-invalid');
            if (aviso) { aviso.remove(); }
            return true;
        }
        if (!aviso) {
            aviso = document.createElement('div');
            aviso.className = 'invalid-feedback aviso-validacion';
            campo.insertAdjacentElement('afterend', aviso);
        }
        aviso.textContent = mensaje;
        campo.classList.add('is-invalid');
        return false;
    }

    function revisarRut(campo) {
        var valor = campo.value.trim();
        if (!valor) { return marcar(campo, ''); }
        if (!rutValido(valor)) {
            return marcar(campo, 'RUT no válido: el dígito verificador no corresponde al número.');
        }
        campo.value = formatearRut(valor);
        return marcar(campo, '');
    }

    function revisarTelefono(campo) {
        var valor = campo.value.trim();
        if (!valor) { return marcar(campo, ''); }
        var telefono = normalizarTelefono(valor);
        if (telefono === null) {
            return marcar(campo, 'Escriba un teléfono chileno de 9 dígitos, por ejemplo 9 1234 5678 o +56 51 220 6600.');
        }
        campo.value = telefono;
        return marcar(campo, '');
    }

    // Solo campos de texto (no casillas ni opciones que lleven un dato data-*)
    var CAMPOS_RUT = 'input[data-rut]:not([type=radio]):not([type=checkbox]):not([type=hidden])';
    var CAMPOS_TELEFONO = 'input[data-telefono]:not([type=radio]):not([type=checkbox]):not([type=hidden])';

    function conectar(raiz) {
        raiz.querySelectorAll(CAMPOS_RUT).forEach(function (campo) {
            campo.addEventListener('blur', function () { revisarRut(campo); });
            campo.addEventListener('input', function () { if (!campo.value) { marcar(campo, ''); } });
        });
        raiz.querySelectorAll(CAMPOS_TELEFONO).forEach(function (campo) {
            campo.addEventListener('blur', function () { revisarTelefono(campo); });
            campo.addEventListener('input', function () { if (!campo.value) { marcar(campo, ''); } });
        });
        // No se envía un formulario con un RUT o teléfono mal escrito: se marca y se lleva el cursor al campo
        raiz.querySelectorAll('form').forEach(function (formulario) {
            formulario.addEventListener('submit', function (evento) {
                var malos = [];
                formulario.querySelectorAll(CAMPOS_RUT).forEach(function (c) {
                    if (!revisarRut(c) && c.dataset.rut !== 'solo-aviso') { malos.push(c); }
                });
                formulario.querySelectorAll(CAMPOS_TELEFONO).forEach(function (c) { if (!revisarTelefono(c)) { malos.push(c); } });
                if (malos.length) {
                    evento.preventDefault();
                    evento.stopImmediatePropagation();
                    malos[0].focus();
                }
            });
        });
    }

    window.SGR = { limpiarRut: limpiarRut, rutValido: rutValido, formatearRut: formatearRut,
                   normalizarTelefono: normalizarTelefono };
    document.addEventListener('DOMContentLoaded', function () { conectar(document); });
})();
