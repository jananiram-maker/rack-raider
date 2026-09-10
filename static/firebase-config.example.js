/**
 * Firebase Web App configuration.
 *
 * Fill this in with your Firebase project's actual config — NOT the GCP
 * service account used by the backend. This is the public, client-side
 * config object, safe to ship in frontend code (Firebase secures access via
 * Firestore/Auth rules, not by hiding this object).
 *
 * Find it at: Firebase Console → Project Settings (gear icon) → General tab
 * → "Your apps" → Web app → SDK setup and configuration → Config.
 * (If you don't have a Web app registered yet under your GCP project, add
 * one there first — it takes a few seconds and doesn't require new infra.)
 *
 * Also make sure the Google sign-in provider is enabled under
 * Authentication → Sign-in method → Google, or the sign-in button below
 * will fail.
 */
const FIREBASE_CONFIG = {
  apiKey: "REPLACE_WITH_YOUR_FIREBASE_API_KEY",
  authDomain: "REPLACE_WITH_YOUR_PROJECT_ID.firebaseapp.com",
  projectId: "REPLACE_WITH_YOUR_PROJECT_ID",
  storageBucket: "REPLACE_WITH_YOUR_PROJECT_ID.appspot.com",
  messagingSenderId: "REPLACE_WITH_YOUR_SENDER_ID",
  appId: "REPLACE_WITH_YOUR_APP_ID"
};
