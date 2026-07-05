import { initializeApp } from "https://www.gstatic.com/firebasejs/10.8.0/firebase-app.js";
import { getAuth, signInWithEmailAndPassword, signOut, onAuthStateChanged } from "https://www.gstatic.com/firebasejs/10.8.0/firebase-auth.js";

const firebaseConfig = {
    apiKey: "AIzaSyA80IB4rvoqoTo0FCaJhg48bWjSm1n2I4g",
    authDomain: "covered-calls-ab5d1.firebaseapp.com",
    projectId: "covered-calls-ab5d1",
    storageBucket: "covered-calls-ab5d1.firebasestorage.app",
    messagingSenderId: "395032013974",
    appId: "1:395032013974:web:ee980f78db6ce8502fe6b7",
    measurementId: "G-YFWTHS1GY3"
};

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);

export { signInWithEmailAndPassword, signOut, onAuthStateChanged };
