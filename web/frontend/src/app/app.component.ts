import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { PeajeService } from './services/peaje.service';

declare var Pusher: any;

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <!-- PANTALLA DE LOGIN EXCLUSIVO CON GOOGLE OAUTH 2.0 -->
    <div *ngIf="!servicio.usuario" class="min-h-screen flex items-center justify-center p-6 bg-slate-950">
      <div class="max-w-md w-full bg-slate-900 border border-slate-800 rounded-2xl p-8 shadow-2xl">
        <div class="text-center mb-6">
          <span class="px-3 py-1 rounded-full text-xs font-semibold bg-blue-500/20 text-blue-400 border border-blue-500/30">
            IAM-811 · Machine Learning y Aprendizaje Profundo
          </span>
          <h1 class="text-2xl font-bold text-white mt-3">Sistema Inteligente de Control de Peaje</h1>
          <p class="text-slate-400 text-sm mt-1">Autenticación exclusiva con Google OAuth 2.0 (Lista Blanca)</p>
        </div>

        <div *ngIf="errorLogin" class="mb-4 p-4 rounded-xl bg-rose-950/80 border border-rose-500/50 text-rose-200 text-sm">
          <strong>⛔ Acceso Denegado (403)</strong>
          <p class="mt-1">{{ errorLogin }}</p>
        </div>

        <div class="space-y-3">
          <button (click)="iniciarConCuentaGoogle('guamilkar@gmail.com')"
            class="w-full py-3 px-4 rounded-xl bg-white text-slate-900 font-semibold flex items-center justify-center gap-3 hover:bg-slate-100 transition">
            <span>🔐</span> Ingresar con Google: guamilkar&#64;gmail.com (Admin)
          </button>
          <button (click)="iniciarConCuentaGoogle('doc.alvaro.pinto.ma@unifranz.edu.bo')"
            class="w-full py-3 px-4 rounded-xl bg-blue-600 text-white font-semibold flex items-center justify-center gap-3 hover:bg-blue-500 transition">
            <span>🎓</span> Ingresar con Google Docente: doc.alvaro.pinto.ma&#64;unifranz.edu.bo
          </button>
          <button (click)="iniciarConCuentaGoogle('operador.peaje@unifranz.edu.bo')"
            class="w-full py-2.5 px-4 rounded-xl bg-slate-800 text-slate-200 text-sm font-medium hover:bg-slate-700 transition">
            👮 Ingresar como Operador: operador.peaje&#64;unifranz.edu.bo
          </button>
          <button (click)="iniciarConCuentaGoogle('cuenta.no.autorizada@gmail.com')"
            class="w-full py-2.5 px-4 rounded-xl bg-rose-950/60 border border-rose-700/50 text-rose-300 text-sm font-medium hover:bg-rose-900/60 transition">
            🚫 Probar Rechazo de Cuenta No Autorizada (Video Sección 8)
          </button>
        </div>
      </div>
    </div>

    <!-- PANEL PRINCIPAL CON LAS 6 PÁGINAS OBLIGATORIAS -->
    <div *ngIf="servicio.usuario" class="min-h-screen bg-slate-950 text-slate-100">
      <header class="border-b border-slate-800 bg-slate-900/90 backdrop-blur sticky top-0 z-30 px-6 py-3 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 class="text-lg font-bold text-white">🛣️ Peaje Inteligente IAM-811 · Panel en Tiempo Real</h1>
          <p class="text-xs text-slate-400">
            Usuario Google: <strong class="text-blue-400">{{ servicio.usuario.email_google }}</strong> ·
            Rol: <span class="uppercase px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-semibold">{{ servicio.usuario.rol }}</span>
          </p>
        </div>

        <nav class="flex flex-wrap gap-2">
          <button *ngFor="let p of paginas"
            (click)="cambiarPagina(p.id)"
            [class]="paginaActiva === p.id ? 'px-3.5 py-2 rounded-xl bg-blue-600 text-white text-sm font-semibold' : 'px-3.5 py-2 rounded-xl bg-slate-800 text-slate-300 text-sm hover:bg-slate-700'">
            {{ p.icono }} {{ p.titulo }}
          </button>
          <button (click)="salir()" class="px-3 py-2 rounded-xl bg-rose-900/60 text-rose-200 text-sm hover:bg-rose-800">
            Salir
          </button>
        </nav>
      </header>

      <main class="max-w-7xl mx-auto p-6">
        <!-- 1. PANEL EN TIEMPO REAL -->
        <section *ngIf="paginaActiva === 'panel'" class="space-y-6">
          <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div class="p-5 rounded-2xl bg-slate-900 border border-slate-800">
              <span class="text-xs text-slate-400 uppercase">Total Pasos Registrados</span>
              <p class="text-3xl font-bold text-white mt-1">{{ resumen?.total_pasos || 0 }}</p>
            </div>
            <div class="p-5 rounded-2xl bg-slate-900 border border-slate-800">
              <span class="text-xs text-slate-400 uppercase">Recaudación Acumulada</span>
              <p class="text-3xl font-bold text-emerald-400 mt-1">Bs {{ (resumen?.recaudacion_total || 0) | number:'1.2-2' }}</p>
            </div>
            <div class="p-5 rounded-2xl bg-slate-900 border border-slate-800">
              <span class="text-xs text-slate-400 uppercase">Pasajeros Contados (Bono M4)</span>
              <p class="text-3xl font-bold text-cyan-400 mt-1">{{ resumen?.pasajeros_total || 0 }}</p>
            </div>
            <div class="p-5 rounded-2xl bg-slate-900 border border-slate-800">
              <span class="text-xs text-slate-400 uppercase">Alertas Pendientes</span>
              <p class="text-3xl font-bold text-rose-400 mt-1">{{ resumen?.alertas_pendientes || 0 }}</p>
            </div>
          </div>
        </section>
      </main>
    </div>
  `,
})
export class AppComponent implements OnInit, OnDestroy {
  paginaActiva = 'panel';
  paginas = [
    { id: 'panel', titulo: 'Panel en Tiempo Real', icono: '⚡' },
    { id: 'vehiculos', titulo: 'Vehículos (CRUD)', icono: '🚗' },
    { id: 'pasos', titulo: 'Historial de Pasos', icono: '📸' },
    { id: 'alertas', titulo: 'Alertas', icono: '🚨' },
    { id: 'chat', titulo: 'Agente Conversacional', icono: '🤖' },
    { id: 'estado', titulo: 'Estado Inferencia', icono: '☁️' },
  ];

  errorLogin = '';
  resumen: any = null;
  vehiculos: any[] = [];
  pasos: any[] = [];
  alertas: any[] = [];
  estadoInferencia: any = null;
  ultimoIdEvento = 0;
  timerSub: any = null;

  constructor(public servicio: PeajeService) {}

  ngOnInit(): void {
    if (this.servicio.usuario) {
      this.cargarTodo();
      this.iniciarTiempoReal();
    }
  }

  ngOnDestroy(): void {
    if (this.timerSub) {
      clearInterval(this.timerSub);
    }
  }

  iniciarConCuentaGoogle(email: string): void {
    this.errorLogin = '';
    this.servicio.loginConGoogle({ email_google: email }).subscribe({
      next: (res) => {
        this.servicio.guardarSesion(res.token, res.usuario);
        this.cargarTodo();
        this.iniciarTiempoReal();
      },
      error: (err) => {
        this.errorLogin = err.error?.mensaje || 'Acceso denegado: Cuenta fuera de lista blanca.';
      },
    });
  }

  cambiarPagina(id: string): void {
    this.paginaActiva = id;
    this.cargarTodo();
  }

  cargarTodo(): void {
    this.servicio.obtenerDashboard().subscribe((r) => {
      this.resumen = r;
      this.pasos = r.ultimos_pasos || [];
      this.alertas = r.ultimas_alertas || [];
      this.ultimoIdEvento = r.ultimo_id_evento || this.ultimoIdEvento;
    });
    this.servicio.listarVehiculos().subscribe((r) => (this.vehiculos = r.vehiculos || []));
    this.servicio.obtenerEstadoInferencia().subscribe((r) => (this.estadoInferencia = r));
  }

  iniciarTiempoReal(): void {
    if (this.timerSub) clearInterval(this.timerSub);
    this.timerSub = setInterval(() => {
      if (!this.servicio.usuario) return;
      this.servicio.obtenerEventosDesde(this.ultimoIdEvento).subscribe((r) => {
        if (r.eventos && r.eventos.length > 0) {
          this.ultimoIdEvento = r.ultimo_id_evento;
          this.cargarTodo();
        }
      });
    }, 2000);
  }

  salir(): void {
    this.servicio.cerrarSesion();
  }
}
