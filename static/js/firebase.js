
import { initializeApp } from
    "https://www.gstatic.com/firebasejs/11.10.0/firebase-app.js";

import {
    getAuth,
    createUserWithEmailAndPassword,
    signInWithEmailAndPassword,
    signOut,
    onAuthStateChanged
} from "https://www.gstatic.com/firebasejs/11.10.0/firebase-auth.js";

import { getFirestore } from
    "https://www.gstatic.com/firebasejs/11.10.0/firebase-firestore.js";


// ======================================
// 1. FIREBASE CONFIGURATION
// ======================================

const firebaseConfig = {
    apiKey: "AIzaSyAG6SoVqk10iRtefYHAlfRBK69oi0NmNG4",
    authDomain: "cloudvideoprocessor.firebaseapp.com",
    projectId: "cloudvideoprocessor",
    storageBucket: "cloudvideoprocessor.firebasestorage.app",
    messagingSenderId: "159845918188",
    appId: "1:159845918188:web:27b71506b871cdddc94cc9"
};


// ======================================
// 2. INITIALIZE FIREBASE
// ======================================

const app = initializeApp(firebaseConfig);

export const auth = getAuth(app);
export const db = getFirestore(app);


// ======================================
// 3. REGISTER USER
// ======================================

export async function registerUser(email, password) {
    const result = await createUserWithEmailAndPassword(
        auth,
        email,
        password
    );

    return result.user;
}


// ======================================
// 4. LOGIN USER
// ======================================

export async function loginUser(email, password) {
    const result = await signInWithEmailAndPassword(
        auth,
        email,
        password
    );

    return result.user;
}


// ======================================
// 5. LOGOUT USER
// ======================================

export async function logoutUser() {
    await signOut(auth);
}


// ======================================
// 6. AUTHENTICATION STATE
// ======================================

export function observeAuth(callback) {
    return onAuthStateChanged(auth, callback);
}


// ======================================
// 7. GET FIREBASE ID TOKEN
// ======================================

export async function getUserToken() {
    const user = auth.currentUser;

    if (!user) {
        throw new Error("User is not logged in");
    }

    return await user.getIdToken();
}
