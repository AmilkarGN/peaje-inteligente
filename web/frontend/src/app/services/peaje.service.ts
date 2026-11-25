import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';

@Injectable({
  providedIn: 'root',
})
export class PeajeService {
  // Apunta al subdominio HTTPS en producción (o ruta relativa cuando Django sirve el build de Angular)
  public apiBase = '/api/v1';
  public token: string = localStorage.getItem('peaje_token') || '';
  public usuario: any = JSON.parse(localStorage.getItem('peaje_usuario') || 'null');

  constructor(private http: HttpClient) {}

  private headers(): HttpHeaders {
    return new HttpHeaders({
      Authorization: `Bearer ${this.token}`,
    });
  }

  loginConGoogle(payload: { token?: string; email_google?: string }): Observable<any> {
    return this.http.post(`${this.apiBase}/auth/google`, payload);
  }

  guardarSesion(token: string, usuario: any): void {
    this.token = token;
    this.usuario = usuario;
    localStorage.setItem('peaje_token', token);
    localStorage.setItem('peaje_usuario', JSON.stringify(usuario));
  }

  cerrarSesion(): void {
    this.token = '';
    this.usuario = null;
    localStorage.removeItem('peaje_token');
    localStorage.removeItem('peaje_usuario');
  }

  obtenerDashboard(): Observable<any> {
    return this.http.get(`${this.apiBase}/dashboard/resumen`, { headers: this.headers() });
  }

  registrarPasoFrame(payload: { imagen_base64: string; caseta_id: number }): Observable<any> {
    return this.http.post(`${this.apiBase}/pasos/frame`, payload, { headers: this.headers() });
  }

  consultarPlacaTexto(placa: string): Observable<any> {
    return this.http.post(`${this.apiBase}/placas/consultar`, { placa }, { headers: this.headers() });
  }

  consultarPlacaImagen(imagen_base64: string): Observable<any> {
    return this.http.post(`${this.apiBase}/placas/consultar-imagen`, { imagen_base64 }, { headers: this.headers() });
  }

  historialPlaca(placa: string): Observable<any> {
    return this.http.get(`${this.apiBase}/placas/${encodeURIComponent(placa)}/historial`, { headers: this.headers() });
  }

  resumenCaseta(casetaId: number): Observable<any> {
    return this.http.get(`${this.apiBase}/casetas/${casetaId}/resumen`, { headers: this.headers() });
  }

  enviarMensajeAgente(payload: { mensaje?: string; imagen_base64?: string }): Observable<any> {
    return this.http.post(`${this.apiBase}/agente/chat`, payload, { headers: this.headers() });
  }

  listarVehiculos(q: string = ''): Observable<any> {
    return this.http.get(`${this.apiBase}/vehiculos?q=${encodeURIComponent(q)}`, { headers: this.headers() });
  }

  crearVehiculo(vehiculo: any): Observable<any> {
    return this.http.post(`${this.apiBase}/vehiculos`, vehiculo, { headers: this.headers() });
  }

  actualizarVehiculo(id: number, vehiculo: any): Observable<any> {
    return this.http.put(`${this.apiBase}/vehiculos/${id}`, vehiculo, { headers: this.headers() });
  }

  eliminarVehiculo(id: number): Observable<any> {
    return this.http.delete(`${this.apiBase}/vehiculos/${id}`, { headers: this.headers() });
  }

  listarPasos(): Observable<any> {
    return this.http.get(`${this.apiBase}/pasos`, { headers: this.headers() });
  }

  listarAlertas(): Observable<any> {
    return this.http.get(`${this.apiBase}/alertas`, { headers: this.headers() });
  }

  atenderAlerta(id: number): Observable<any> {
    return this.http.patch(`${this.apiBase}/alertas/${id}`, { atendida: true }, { headers: this.headers() });
  }

  obtenerEstadoInferencia(): Observable<any> {
    return this.http.get(`${this.apiBase}/estado-inferencia`, { headers: this.headers() });
  }

  obtenerEventosDesde(ultimoId: number): Observable<any> {
    return this.http.get(`${this.apiBase}/eventos/stream?desde=${ultimoId}`, { headers: this.headers() });
  }

  listarImagenesPrueba(): Observable<any> {
    return this.http.get(`${this.apiBase}/imagenes-prueba`, { headers: this.headers() });
  }

  cargarImagenPrueba(nombre: string): Observable<any> {
    return this.http.get(`${this.apiBase}/imagenes-prueba?archivo=${encodeURIComponent(nombre)}`, {
      headers: this.headers(),
    });
  }
}
