/**
 * Energy API Client
 * 
 * Axios instance for Energy Vertical API communication.
 * Base configuration for all API calls.
 */

import axios from 'axios';

const ENERGY_API_BASE_URL = process.env.NEXT_PUBLIC_ENERGY_API_URL || 'http://localhost:8700';

export const energyApi = axios.create({
    baseURL: ENERGY_API_BASE_URL,
    timeout: 10000,
    headers: {
        'Content-Type': 'application/json'
    }
});

// Request interceptor (for future auth if needed)
energyApi.interceptors.request.use(
    (config) => {
        // Future: Add auth token here
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

// Response interceptor (error handling)
energyApi.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.response) {
            // Server responded with error status
            console.error('API Error:', {
                status: error.response.status,
                data: error.response.data,
                url: error.config.url
            });
        } else if (error.request) {
            // Request made but no response
            console.error('Network Error:', error.message);
        } else {
            // Something else happened
            console.error('Request Error:', error.message);
        }

        return Promise.reject(error);
    }
);
