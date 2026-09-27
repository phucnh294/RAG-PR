// Register Account page behaviour. Every rule here is stated word for word in the Agents
// pipeline's default requirement (backend rag_backend/agents/defaults.py) — change both
// together, or the business agent will "confirm" rules the page doesn't implement.
(function () {
  "use strict";

  var FIRST_ACCOUNT_ID = 123;
  var COUNTER_KEY = "myweb.nextAccountId";
  var NAME_MAX_LENGTH = 50;
  var EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  var DOB_PATTERN = /^(\d{2})\/(\d{2})\/(\d{4})$/;

  var form = document.getElementById("register-form");
  var banner = document.getElementById("success-banner");
  var backButton = document.getElementById("back");

  function readCounter() {
    try {
      var stored = parseInt(window.localStorage.getItem(COUNTER_KEY) || "", 10);
      return isNaN(stored) ? FIRST_ACCOUNT_ID : stored;
    } catch (e) {
      return FIRST_ACCOUNT_ID;
    }
  }

  function writeCounter(value) {
    try {
      window.localStorage.setItem(COUNTER_KEY, String(value));
    } catch (e) {
      // Storage blocked: the next account reuses the same number, which is fine for a demo.
    }
  }

  function validateName(value, label) {
    if (!value) return label + " is required.";
    if (value.length > NAME_MAX_LENGTH) {
      return label + " must be at most " + NAME_MAX_LENGTH + " characters.";
    }
    return "";
  }

  function validateEmail(value) {
    if (!value) return "Email is required.";
    if (!EMAIL_PATTERN.test(value)) return "Email must be a valid email address.";
    return "";
  }

  function validateDob(value) {
    if (!value) return "";
    var match = DOB_PATTERN.exec(value);
    if (!match) return "Date of birth must be in DD/MM/YYYY format.";
    var day = parseInt(match[1], 10);
    var month = parseInt(match[2], 10);
    var year = parseInt(match[3], 10);
    var date = new Date(year, month - 1, day);
    var isRealDate =
      date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day;
    if (!isRealDate) return "Date of birth must be in DD/MM/YYYY format.";
    if (date.getTime() > Date.now()) return "Date of birth cannot be in the future.";
    return "";
  }

  function setError(fieldId, message) {
    var input = document.getElementById(fieldId);
    var error = document.getElementById(fieldId + "-error");
    error.textContent = message;
    error.hidden = !message;
    if (message) {
      input.setAttribute("aria-invalid", "true");
    } else {
      input.removeAttribute("aria-invalid");
    }
  }

  function clearErrors() {
    ["firstName", "lastName", "dob", "email"].forEach(function (id) {
      setError(id, "");
    });
  }

  function hideBanner() {
    banner.hidden = true;
    banner.textContent = "";
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    hideBanner();

    var values = {
      firstName: form.firstName.value.trim(),
      lastName: form.lastName.value.trim(),
      dob: form.dob.value.trim(),
      email: form.email.value.trim(),
    };
    var errors = {
      firstName: validateName(values.firstName, "First name"),
      lastName: validateName(values.lastName, "Last name"),
      dob: validateDob(values.dob),
      email: validateEmail(values.email),
    };

    var firstInvalid = null;
    Object.keys(errors).forEach(function (id) {
      setError(id, errors[id]);
      if (errors[id] && !firstInvalid) firstInvalid = id;
    });
    if (firstInvalid) {
      document.getElementById(firstInvalid).focus();
      return;
    }

    var accountId = readCounter();
    writeCounter(accountId + 1);
    form.reset();
    banner.textContent = "Account " + accountId + " has been created successfully!";
    banner.hidden = false;
  });

  backButton.addEventListener("click", function () {
    form.reset();
    clearErrors();
    hideBanner();
    // Only navigate back when we came from another page on this site; opened directly
    // (as the tests do), Back just resets the form.
    if (document.referrer && document.referrer.indexOf(window.location.origin) === 0) {
      window.history.back();
    }
  });
})();
