import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { PeajeService } from './services/peaje.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div *ngIf="!servicio.usuario" class="min-h-screen flex items-center justify-center p-4 bg-slate-50 text-slate-900">
      <div class="max-w-md w-full bg-white border border-slate-200 rounded-2xl p-8 shadow-sm">
        <div class="text-center mb-6">
          <span class="inline-block px-3 py-1 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
            IAM-811 · Machine Learning y Aprendizaje Profundo
          </span>
          <h1 class="text-2xl font-bold text-slate-900 mt-3">Sistema Inteligente de Control de Peaje</h1>
          <p class="text-slate-500 text-sm mt-1">Autenticación exclusiva con Google OAuth 2.0 (Lista Blanca)</p>
        </div>

        <div *ngIf="errorLogin" class="mb-4 p-4 rounded-xl bg-red-50 border border-red-200 text-red-800 text-sm">
          <strong>Acceso Denegado (403)</strong>
          <p class="mt-1">{{ errorLogin }}</p>
        </div>

        <div class="space-y-2.5">
          <button (click)="iniciarConCuentaGoogle('doc.alvaro.pinto.ma@unifranz.edu.bo')"
            class="w-full py-3 px-4 rounded-xl bg-white border border-slate-200 hover:border-blue-400 text-slate-900 font-semibold flex items-center justify-between transition">
            <span class="truncate">doc.alvaro.pinto.ma&#64;unifranz.edu.bo</span>
            <span class="px-2 py-0.5 rounded bg-blue-100 text-blue-800 text-xs">Admin</span>
          </button>
          <button (click)="iniciarConCuentaGoogle('guamilkar@gmail.com')"
            class="w-full py-3 px-4 rounded-xl bg-white border border-slate-200 hover:border-blue-400 text-slate-900 font-semibold flex items-center justify-between transition">
            <span class="truncate">guamilkar&#64;gmail.com</span>
            <span class="px-2 py-0.5 rounded bg-blue-100 text-blue-800 text-xs">Admin</span>
          </button>
          <button (click)="iniciarConCuentaGoogle('operador.peaje@unifranz.edu.bo')"
            class="w-full py-2.5 px-4 rounded-xl bg-white border border-slate-200 text-slate-700 text-sm font-medium flex items-center justify-between transition">
            <span class="truncate">operador.peaje&#64;unifranz.edu.bo</span>
            <span class="px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 text-xs">Operador</span>
          </button>
          <button (click)="iniciarConCuentaGoogle('cuenta.no.autorizada@gmail.com')"
            class="w-full py-2.5 px-4 rounded-xl bg-red-50 border border-red-200 text-red-800 text-sm font-medium flex items-center justify-between transition">
            <span class="truncate">cuenta.no.autorizada&#64;gmail.com</span>
            <span class="px-2 py-0.5 rounded bg-red-100 text-red-800 text-xs">Rechazo 403</span>
          </button>
        </div>
      </div>
    </div>

    <div *ngIf="servicio.usuario" class="min-h-screen bg-slate-50 text-slate-900">
      <header class="border-b border-slate-200 bg-white sticky top-0 z-30 px-6 py-3 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 class="text-lg font-bold text-slate-900">Peaje Inteligente IAM-811 · Panel en Tiempo Real</h1>
          <p class="text-xs text-slate-500">
            Usuario Google: <strong class="text-blue-700">{{ servicio.usuario.email_google }}</strong> ·
            Rol: <span class="uppercase px-2 py-0.5 rounded bg-blue-50 text-blue-700 font-semibold">{{ servicio.usuario.rol }}</span>
          </p>
        </div>

        <nav class="flex flex-wrap gap-2">
          <button *ngFor="let p of paginas"
            (click)="cambiarPagina(p.id)"
            [class]="paginaActiva === p.id ? 'px-3.5 py-2 rounded-lg bg-blue-600 text-white text-sm font-semibold' : 'px-3.5 py-2 rounded-lg bg-slate-100 text-slate-700 text-sm hover:bg-slate-200'">
            {{ p.titulo }}
          </button>
          <button (click)="salir()" class="px-3 py-2 rounded-lg bg-white border border-slate-300 text-slate-700 text-sm hover:bg-slate-100">
            Salir
          </button>
        </nav>
      </header>
    </div>
  `,
})
export class AppComponent implements OnInit, OnDestroy {
  paginaActiva = 'panel';
  paginas = [
    { id: 'panel', titulo: 'Panel en Tiempo Real' },
    { id: 'vehiculos', titulo: 'Vehículos (CRUD)' },
    { id: 'pasos', titulo: 'Historial de Pasos' },
    { id: 'alertas', titulo: 'Alertas' },
    { id: 'chat', titulo: 'Agente Conversacional' },
    { id: 'estado', titulo: 'Estado Inferencia' },
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
    if (this.timerSub) clearInterval(this.timerSub);
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
