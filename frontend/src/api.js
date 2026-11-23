const API_BASE = '/api/v1';

export const getAuthHeaders = () => {
  const session = JSON.parse(localStorage.getItem('netracare_user') || '{}');
  const headers = { 'Content-Type': 'application/json' };
  if (session.token) {
    headers['Authorization'] = `Bearer ${session.token}`;
  }
  if (session.role) {
    headers['X-Role'] = session.role;
  }
  if (session.user_id) {
    headers['X-User-Id'] = session.user_id;
  }
  if (session.name) {
    headers['X-User-Name'] = session.name;
  }
  return headers;
};

export const api = {
  async login(payload) {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const err = await res.json();
      throw err;
    }
    return res.json();
  },

  async getDoctors() {
    const res = await fetch(`${API_BASE}/doctors`, {
      headers: getAuthHeaders()
    });
    if (!res.ok) throw await res.json();
    return res.json();
  },

  async getDoctorSchedule(doctorId) {
    const res = await fetch(`${API_BASE}/doctors/${doctorId}/schedule`, {
      headers: getAuthHeaders()
    });
    if (!res.ok) throw await res.json();
    return res.json();
  },

  async getSpecialities() {
    const res = await fetch(`${API_BASE}/doctors/specialities`, {
      headers: getAuthHeaders()
    });
    if (!res.ok) throw await res.json();
    return res.json();
  },

  async getFreeSlots(doctorId, date, visitType) {
    const params = new URLSearchParams({
      doctor_id: doctorId,
      date,
      visit_type: visitType
    });
    const res = await fetch(`${API_BASE}/slots?${params.toString()}`, {
      headers: getAuthHeaders()
    });
    if (!res.ok) throw await res.json();
    return res.json();
  },

  async getAppointments(filters = {}) {
    const params = new URLSearchParams();
    if (filters.date) params.append('date', filters.date);
    if (filters.doctor_id) params.append('doctor_id', filters.doctor_id);
    if (filters.patient_id) params.append('patient_id', filters.patient_id);

    const res = await fetch(`${API_BASE}/appointments?${params.toString()}`, {
      headers: getAuthHeaders()
    });
    if (!res.ok) throw await res.json();
    return res.json();
  },

  async createAppointment(data) {
    const res = await fetch(`${API_BASE}/appointments`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(data)
    });
    if (!res.ok) {
      const err = await res.json();
      throw err;
    }
    return res.json();
  },

  async cancelAppointment(appointmentId) {
    const res = await fetch(`${API_BASE}/appointments/${appointmentId}/cancel`, {
      method: 'POST',
      headers: getAuthHeaders()
    });
    if (!res.ok) {
      const err = await res.json();
      throw err;
    }
    return res.json();
  },

  async completeAppointment(appointmentId, doctorNote) {
    const res = await fetch(`${API_BASE}/appointments/${appointmentId}/complete`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ doctor_note: doctorNote })
    });
    if (!res.ok) {
      const err = await res.json();
      throw err;
    }
    return res.json();
  },

  async rescheduleAppointment(appointmentId, data) {
    const res = await fetch(`${API_BASE}/appointments/${appointmentId}/reschedule`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(data)
    });
    if (!res.ok) {
      const err = await res.json();
      throw err;
    }
    return res.json();
  },

  async getFactOfTheDay(previous = null) {
    const url = previous 
      ? `${API_BASE}/fact-of-the-day?previous=${encodeURIComponent(previous)}`
      : `${API_BASE}/fact-of-the-day`;
    const res = await fetch(url, {
      headers: getAuthHeaders()
    });
    if (!res.ok) throw await res.json();
    return res.json();
  },

  async getUrgentCases(unseenOnly = true) {
    const res = await fetch(`${API_BASE}/urgent-cases?unseen_only=${unseenOnly}`, {
      headers: getAuthHeaders()
    });
    if (!res.ok) throw await res.json();
    return res.json();
  },

  async markUrgentCaseSeen(caseId) {
    const res = await fetch(`${API_BASE}/urgent-cases/${caseId}/seen`, {
      method: 'POST',
      headers: getAuthHeaders()
    });
    if (!res.ok) throw await res.json();
    return res.json();
  },

  async getDoctorPatientSummary(patientId, appointmentId = null) {
    const url = appointmentId 
      ? `${API_BASE}/doctor/patients/${patientId}/summary?appointment_id=${encodeURIComponent(appointmentId)}`
      : `${API_BASE}/doctor/patients/${patientId}/summary`;
    const res = await fetch(url, {
      headers: getAuthHeaders()
    });
    if (!res.ok) throw await res.json();
    return res.json();
  },

  async sendChatMessage(message, threadId = null, history = []) {
    const payload = { message };
    if (threadId) payload.thread_id = threadId;
    const res = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const err = await res.json();
      throw err;
    }
    return res.json();
  },

  async confirmChatAction(threadId, confirm) {
    const res = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ thread_id: threadId, confirm })
    });
    if (!res.ok) {
      const err = await res.json();
      throw err;
    }
    return res.json();
  },

  async getSearchDebug(query) {
    const res = await fetch(`${API_BASE}/staff/search-debug?q=${encodeURIComponent(query)}`, {
      headers: getAuthHeaders()
    });
    if (!res.ok) {
      const err = await res.json();
      throw err;
    }
    return res.json();
  },

  async getStaffApprovals(status = 'pending') {
    const res = await fetch(`${API_BASE}/staff/approvals?status=${status}`, {
      headers: getAuthHeaders()
    });
    if (!res.ok) {
      const err = await res.json();
      throw err;
    }
    return res.json();
  },

  async approveStaffRequest(id) {
    const res = await fetch(`${API_BASE}/staff/approvals/${id}/approve`, {
      method: 'POST',
      headers: getAuthHeaders()
    });
    if (!res.ok) {
      const err = await res.json();
      throw err;
    }
    return res.json();
  },

  async rejectStaffRequest(id) {
    const res = await fetch(`${API_BASE}/staff/approvals/${id}/reject`, {
      method: 'POST',
      headers: getAuthHeaders()
    });
    if (!res.ok) {
      const err = await res.json();
      throw err;
    }
    return res.json();
  }
};
