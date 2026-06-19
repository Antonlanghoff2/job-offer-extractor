// Copyright Anton Langhoff <anton@langhoff.fr>
// SPDX-License-Identifier: MIT

document.addEventListener('DOMContentLoaded', () => {
  const collections = {
    competences: {
      list: document.getElementById('skills-list'),
      template: document.getElementById('skill-template'),
    },
    formations: {
      list: document.getElementById('education-list'),
      template: document.getElementById('formation-template'),
    },
    experiences_professionnelles: {
      list: document.getElementById('experience-list'),
      template: document.getElementById('experience-template'),
    },
  };

  function updateAttributes(item, collectionName, index) {
    item.dataset.index = String(index);
    item.querySelectorAll('[name]').forEach((element) => {
      const name = element.getAttribute('name');
      if (!name) {
        return;
      }
      const updated = name
        .replace(/^competences\[\d+\]/, `${collectionName}[${index}]`)
        .replace(/^formations\[\d+\]/, `${collectionName}[${index}]`)
        .replace(/^experiences_professionnelles\[\d+\]/, `${collectionName}[${index}]`);
      element.setAttribute('name', updated);
    });
  }

  function reindex(collectionName) {
    const config = collections[collectionName];
    if (!config || !config.list) {
      return;
    }
    Array.from(config.list.querySelectorAll('[data-item]')).forEach((item, index) => {
      updateAttributes(item, collectionName, index);
    });
  }

  function createItem(collectionName) {
    const config = collections[collectionName];
    if (!config || !config.template) {
      return null;
    }
    const fragment = config.template.content.cloneNode(true);
    const item = fragment.querySelector('[data-item]');
    if (!item) {
      return null;
    }
    item.querySelectorAll('input, textarea, select').forEach((element) => {
      if (element.tagName === 'TEXTAREA') {
        element.value = '';
        return;
      }
      if (element.type === 'hidden') {
        return;
      }
      if (element.type === 'checkbox' || element.type === 'radio') {
        element.checked = false;
        return;
      }
      if (element.name.endsWith('[source]')) {
        element.value = collectionName === 'competences' ? 'explicite' : 'cv';
        return;
      }
      if (element.name.endsWith('[confiance]')) {
        element.value = '0';
        return;
      }
      element.value = '';
    });
    return fragment;
  }

  function addItem(collectionName) {
    const config = collections[collectionName];
    const fragment = createItem(collectionName);
    if (!config || !config.list || !fragment) {
      return;
    }
    config.list.appendChild(fragment);
    reindex(collectionName);
  }

  function bindSection(collectionName) {
    const config = collections[collectionName];
    if (!config || !config.list) {
      return;
    }
    const addButton = document.querySelector(`.js-add-item[data-target="${collectionName}"]`);
    if (addButton) {
      addButton.addEventListener('click', () => addItem(collectionName));
    }
    config.list.addEventListener('click', (event) => {
      const button = event.target.closest('.js-remove-item');
      if (!button) {
        return;
      }
      const item = button.closest('[data-item]');
      if (!item) {
        return;
      }
      item.remove();
      reindex(collectionName);
    });
  }

  Object.keys(collections).forEach(bindSection);

  const form = document.getElementById('cv-validation-form');
  if (form) {
    form.addEventListener('submit', () => {
      Object.keys(collections).forEach(reindex);
    });
  }
});
